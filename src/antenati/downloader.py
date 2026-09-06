# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Core download orchestration for the Portale Antenati."""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, CancelledError, Future, ThreadPoolExecutor, wait
from contextlib import suppress
from dataclasses import dataclass
from hashlib import sha256
from json import loads
from os import mkdir, path
from pathlib import Path
from re import finditer
from sys import exit as sys_exit
from tempfile import NamedTemporaryFile
from typing import Any

from click import confirm, echo
from requests import RequestException, Response, Session
from slugify import slugify

from antenati import http, iiif, provenance
from antenati import image as image_validation
from antenati.errors import AntenatiError, ResourceLimitError, ThreadError
from antenati.validation import DownloadOptions, validate_download_options, validate_page_range

logger = logging.getLogger(__name__)

DEFAULT_SIZE: int = 0
DEFAULT_N_THREADS: int = 2


@dataclass(frozen=True)
class DownloadLimits:
    """Resource ceilings used to keep malformed/huge sources bounded."""

    max_canvases: int = 20_000
    max_metadata_bytes: int = 20 * 1024 * 1024
    max_image_bytes: int = 512 * 1024 * 1024
    max_total_bytes: int = 20 * 1024 * 1024 * 1024
    in_flight_factor: int = 2


@dataclass
class ProgressBar:
    set_total: Callable[[int], None]
    update: Callable[[], None]


@dataclass(frozen=True)
class DownloadItem:
    canvas: dict[str, Any]
    stem: str
    source_url: str


@dataclass(frozen=True)
class DownloadPlan:
    items: tuple[DownloadItem, ...]
    size: int

    @property
    def expected(self) -> int:
        return len(self.items)


@dataclass(frozen=True)
class PageFailure:
    label: str
    reason: str


@dataclass(frozen=True)
class DownloadReport:
    expected: int
    attempted: int
    completed: int
    skipped: int
    failed: tuple[PageFailure, ...]
    cancelled: bool
    bytes_written: int

    @property
    def successful(self) -> bool:
        return not self.cancelled and not self.failed and self.completed + self.skipped == self.expected

    @property
    def remaining(self) -> int:
        return max(0, self.expected - self.completed - self.skipped - len(self.failed))


class _ByteBudget:
    def __init__(self, limit: int):
        self._limit = limit
        self._used = 0
        self._lock = threading.Lock()

    def consume(self, amount: int) -> None:
        with self._lock:
            if self._used + amount > self._limit:
                raise ResourceLimitError(f'Total download budget exceeded ({self._limit} bytes)')
            self._used += amount


class Downloader:
    """Plan and execute a Portale Antenati gallery download."""

    def __init__(
        self,
        url: str,
        first: int,
        last: int | None,
        descriptive_names: bool = False,
        limits: DownloadLimits | None = None,
    ):
        validate_page_range(first, last)
        if not url.strip():
            from antenati.errors import ValidationError

            raise ValidationError('url must not be empty')
        self.url = url
        self.first = first
        self.last = last
        self.descriptive_names = descriptive_names
        self.limits = limits or DownloadLimits()
        self.session: Session = http.build_session()
        self._manifest: dict[str, Any] | None = None
        self._manifest_url: str | None = None
        self._all_canvases: list[dict[str, Any]] | None = None
        self._canvases: list[dict[str, Any]] | None = None
        self._archive_id: str | None = None
        self._ark_id: str | None = None
        self._dirname: Path | None = None
        self._plan: DownloadPlan | None = None

    @property
    def manifest(self) -> dict[str, Any]:
        self.load()
        assert self._manifest is not None
        return self._manifest

    @property
    def manifest_url(self) -> str:
        self.load()
        assert self._manifest_url is not None
        return self._manifest_url

    @property
    def canvases(self) -> list[dict[str, Any]]:
        self.load()
        assert self._canvases is not None
        return self._canvases

    @property
    def archive_id(self) -> str:
        self.load()
        assert self._archive_id is not None
        return self._archive_id

    @property
    def ark_id(self) -> str:
        self.load()
        assert self._ark_id is not None
        return self._ark_id

    @property
    def dirname(self) -> Path:
        self.load()
        assert self._dirname is not None
        return self._dirname

    @dirname.setter
    def dirname(self, value: Path) -> None:
        self._dirname = value

    @property
    def gallery_length(self) -> int:
        return len(self.canvases)

    def _read_limited(self, response: Response, limit: int) -> bytes:
        data = bytearray()
        try:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                if len(data) + len(chunk) > limit:
                    raise ResourceLimitError(f'Response exceeded metadata limit ({limit} bytes): {response.url}')
                data.extend(chunk)
        finally:
            response.close()
        return bytes(data)

    def _fetch_text(self, url: str) -> str:
        reply = http.fetch(self.session, url, stream=True)
        charset = http.get_content_charset(reply) or 'utf-8'
        return self._read_limited(reply, self.limits.max_metadata_bytes).decode(charset)

    def load(self) -> Downloader:
        if self._manifest is not None:
            return self
        archive_id = None if iiif.is_manifest_url(self.url) else iiif.get_archive_id_from_url(self.url)
        logger.info('Loading manifest from %s', self.url)
        manifest, manifest_url = self._load_manifest()
        all_canvases = iiif.slice_canvases(manifest, 0, None)
        if len(all_canvases) > self.limits.max_canvases:
            raise ResourceLimitError(f'Manifest contains {len(all_canvases)} canvases; limit is {self.limits.max_canvases}')
        canvases = iiif.slice_canvases(manifest, self.first, self.last)
        if archive_id is None:
            archive_id = iiif.get_archive_id_from_canvases(all_canvases)
        self._manifest = manifest
        self._manifest_url = manifest_url
        self._all_canvases = all_canvases
        self._canvases = canvases
        self._archive_id = archive_id
        self._ark_id = self._resolve_ark_id(canvases, archive_id)
        self._dirname = self._generate_dirname(manifest, archive_id)
        logger.info('Manifest loaded: %d canvases selected', len(canvases))
        return self

    def plan(self, size: int = DEFAULT_SIZE) -> DownloadPlan:
        if size < 0:
            from antenati.errors import ValidationError

            raise ValidationError('size must be >= 0')
        self.load()
        if self._plan is not None and self._plan.size == size:
            return self._plan
        assert self._all_canvases is not None
        assert self._canvases is not None
        all_stems = self._build_unique_stems(self._all_canvases)
        selected_stems = all_stems[self.first : self.last]
        items = tuple(
            DownloadItem(
                canvas=canvas,
                stem=stem,
                source_url=iiif.manipulate_image_url(iiif.image_url_for_canvas(canvas), size),
            )
            for canvas, stem in zip(self._canvases, selected_stems, strict=True)
        )
        self._plan = DownloadPlan(items=items, size=size)
        return self._plan

    def _load_manifest(self) -> tuple[dict[str, Any], str]:
        if iiif.is_manifest_url(self.url):
            manifest_url = self.url
        else:
            gallery_html = self._fetch_text(self.url)
            manifest_url = iiif.parse_manifest_url_from_html(gallery_html, self.url)
        logger.debug('Manifest URL: %s', manifest_url)
        return loads(self._fetch_text(manifest_url)), manifest_url

    def _resolve_ark_id(self, canvases: list[dict[str, Any]], archive_id: str) -> str:
        first_canvas_url = str(canvases[0].get('@id', ''))
        for candidate in (self.url, first_canvas_url):
            ark = iiif.get_ark_id_from_url(candidate)
            if ark:
                return ark
        return archive_id

    @staticmethod
    def _generate_dirname(manifest: dict[str, Any], archive_id: str) -> Path:
        context = iiif.get_metadata_value(manifest, iiif.META_CONTEXT)
        year = iiif.get_metadata_value(manifest, iiif.META_TITLE)
        typology = iiif.get_metadata_value(manifest, iiif.META_TYPOLOGY)
        return Path(slugify(f'{context}-{year}-{typology}-{archive_id}'))

    @staticmethod
    def _pad_numeric_label(label: str, width: int) -> str:
        matches = list(finditer(r'\d+', label))
        if not matches:
            return label
        match = matches[-1]
        number = match.group(0).zfill(width)
        return f'{label[: match.start()]}{number}{label[match.end() :]}'

    def _build_unique_stems(self, canvases: list[dict[str, Any]]) -> list[str]:
        used: set[str] = set()
        result: list[str] = []
        width = len(str(len(canvases)))
        for index, canvas in enumerate(canvases, start=1):
            raw_label = str(canvas.get('label', ''))
            padded_label = self._pad_numeric_label(raw_label, width)
            label = slugify(padded_label) or f'image-{index:0{width}d}'
            base = label
            if self.descriptive_names:
                image_url = iiif.image_url_for_canvas(canvas)
                base = f'{label}+{self.ark_id}+{iiif.get_image_id_from_url(image_url)}'
            candidate = base
            suffix = 2
            while candidate in used:
                candidate = f'{base}-{suffix}'
                suffix += 1
            used.add(candidate)
            result.append(candidate)
        return result

    def print_gallery_info(self) -> None:
        for entry in self.manifest['metadata']:
            print(f'{entry["label"]:<25}{entry["value"]}')
        print(f'{self.gallery_length} images found.')

    def check_dir(self, parentdir: str | None = None, interactive: bool = True) -> None:
        current = self.dirname
        if parentdir is not None:
            self.dirname = Path(parentdir) / current
        print(f'Output directory: {self.dirname}')
        if path.exists(self.dirname):
            msg = f'Directory {self.dirname} already exists.'
            if not interactive:
                raise RuntimeError(msg)
            echo(msg)
            if not confirm('Do you want to proceed?'):
                sys_exit(1)
        else:
            mkdir(self.dirname)

    @staticmethod
    def _resume_key(item: DownloadItem) -> tuple[str, str]:
        return str(item.canvas.get('@id', '')), item.source_url

    def _thread_main(
        self,
        item: DownloadItem,
        size: int,
        cancel: threading.Event | None,
        budget: _ByteBudget,
    ) -> provenance.ImageRecord:
        label = slugify(str(item.canvas.get('label', ''))) or item.stem
        temp_name: str | None = None
        reply: Response | None = None
        try:
            if cancel is not None and cancel.is_set():
                raise CancelledError
            reply = http.fetch(self.session, item.source_url, stream=True)
            content_type = http.get_content_type(reply)
            extension = image_validation.extension_for_media_type(content_type)
            filename = self.dirname / f'{item.stem}{extension}'
            digest = sha256()
            byte_size = 0
            with NamedTemporaryFile(
                mode='wb',
                dir=self.dirname,
                prefix=f'.{item.stem}.',
                suffix='.tmp',
                delete=False,
            ) as img_file:
                temp_name = img_file.name
                for chunk in reply.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    if cancel is not None and cancel.is_set():
                        raise CancelledError
                    byte_size += len(chunk)
                    if byte_size > self.limits.max_image_bytes:
                        raise ResourceLimitError(f'{item.source_url}: image exceeded {self.limits.max_image_bytes} byte limit')
                    budget.consume(len(chunk))
                    img_file.write(chunk)
                    digest.update(chunk)
                img_file.flush()
                os.fsync(img_file.fileno())
            image_validation.validate_image_file(content_type, Path(temp_name))
            if cancel is not None and cancel.is_set():
                raise CancelledError
            os.replace(temp_name, filename)
            temp_name = None
            return provenance.ImageRecord.create(
                canvas_id=str(item.canvas.get('@id', '')),
                label=str(item.canvas.get('label', '')),
                source_url=item.source_url,
                filename=filename.name,
                requested_size=size,
                byte_size=byte_size,
                sha256=digest.hexdigest(),
            )
        except CancelledError:
            raise
        except (RequestException, AntenatiError, OSError, RuntimeError, ValueError) as ex:
            logger.warning('Image %s failed: %s', label, ex)
            raise ThreadError(label) from ex
        finally:
            if reply is not None:
                reply.close()
            if temp_name is not None:
                with suppress(FileNotFoundError):
                    os.unlink(temp_name)

    def _persist_provenance(self, size: int, records: list[provenance.ImageRecord]) -> None:
        provenance.write_provenance(
            self.dirname,
            source_url=self.url,
            manifest_url=self.manifest_url,
            manifest=self.manifest,
            archive_id=self.archive_id,
            ark_id=self.ark_id,
            requested_size=size,
            records=sorted(records, key=lambda record: record.filename),
        )

    def _in_flight_limit(self, n_workers: int) -> int:
        return max(1, n_workers, n_workers * self.limits.in_flight_factor)

    @staticmethod
    def _fill_futures(
        executor: ThreadPoolExecutor,
        items: Iterator[DownloadItem],
        futures: dict[Future[provenance.ImageRecord], DownloadItem],
        limit: int,
        submit: Callable[[DownloadItem], Future[provenance.ImageRecord]],
    ) -> None:
        del executor
        while len(futures) < limit:
            try:
                item = next(items)
            except StopIteration:
                return
            future = submit(item)
            futures[future] = item

    def run(
        self,
        n_workers: int,
        size: int,
        progress: ProgressBar,
        cancel: threading.Event | None = None,
        *,
        resume: bool = False,
    ) -> DownloadReport:
        validate_download_options(DownloadOptions(first=self.first, last=self.last, size=size, n_workers=n_workers))
        plan = self.plan(size)
        progress.set_total(plan.expected)
        if cancel is not None and cancel.is_set():
            logger.info('Download cancelled before any image work was submitted')
            return DownloadReport(plan.expected, 0, 0, 0, (), True, 0)
        verified = provenance.verified_resume_records(self.dirname, manifest_url=self.manifest_url, requested_size=size) if resume else {}
        records: list[provenance.ImageRecord] = []
        pending: list[DownloadItem] = []
        skipped = 0
        for item in plan.items:
            existing = verified.get(self._resume_key(item))
            if existing is None:
                pending.append(item)
            else:
                records.append(existing)
                skipped += 1
                progress.update()
        attempted = 0
        completed = 0
        bytes_written = 0
        failures: list[PageFailure] = []
        cancelled = False
        budget = _ByteBudget(self.limits.max_total_bytes)
        item_iter = iter(pending)
        in_flight: dict[Future[provenance.ImageRecord], DownloadItem] = {}
        in_flight_limit = self._in_flight_limit(n_workers)
        with ThreadPoolExecutor(max_workers=n_workers) as executor:

            def submit(item: DownloadItem) -> Future[provenance.ImageRecord]:
                return executor.submit(self._thread_main, item, size, cancel, budget)

            self._fill_futures(executor, item_iter, in_flight, in_flight_limit, submit)
            while in_flight:
                done, _ = wait(tuple(in_flight), return_when=FIRST_COMPLETED)
                for future in done:
                    in_flight.pop(future, None)
                    if cancel is not None and cancel.is_set():
                        cancelled = True
                        for waiting in in_flight:
                            waiting.cancel()
                    if future.cancelled():
                        continue
                    attempted += 1
                    progress.update()
                    try:
                        record = future.result()
                    except CancelledError:
                        cancelled = True
                    except ThreadError as ex:
                        failures.append(PageFailure(ex.label, str(ex.__cause__)))
                    else:
                        completed += 1
                        bytes_written += record.byte_size
                        records.append(record)
                if not cancelled:
                    self._fill_futures(executor, item_iter, in_flight, in_flight_limit, submit)
        self._persist_provenance(size, records)
        return DownloadReport(
            expected=plan.expected,
            attempted=attempted,
            completed=completed,
            skipped=skipped,
            failed=tuple(failures),
            cancelled=cancelled,
            bytes_written=bytes_written,
        )
