# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Core download orchestration for the Portale Antenati.

The downloader lifecycle is deliberately split into explicit phases:
construct configuration, load the manifest, build a deterministic plan, then
execute it. Execution returns a structured :class:`DownloadReport` shared by
CLI and GUI callers.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from contextlib import suppress
from dataclasses import dataclass
from json import loads
from mimetypes import guess_extension
from os import mkdir, path
from pathlib import Path
from sys import exit as sys_exit
from tempfile import NamedTemporaryFile
from typing import Any

from click import confirm, echo
from requests import RequestException, Session
from slugify import slugify

from antenati import http, iiif
from antenati.errors import AntenatiError, ThreadError

logger = logging.getLogger(__name__)

DEFAULT_SIZE: int = 0
DEFAULT_N_THREADS: int = 2


@dataclass
class ProgressBar:
    """Callback pair used to drive a progress indicator."""

    set_total: Callable[[int], None]
    update: Callable[[], None]


@dataclass(frozen=True)
class DownloadItem:
    """One planned canvas download, independent from execution order."""

    canvas: dict[str, Any]
    stem: str
    source_url: str


@dataclass(frozen=True)
class DownloadPlan:
    """Immutable execution plan produced from a loaded manifest."""

    items: tuple[DownloadItem, ...]
    size: int

    @property
    def expected(self) -> int:
        return len(self.items)


@dataclass(frozen=True)
class PageFailure:
    """Failure associated with one planned page."""

    label: str
    reason: str


@dataclass(frozen=True)
class DownloadReport:
    """Complete outcome of one execution attempt."""

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


class Downloader:
    """Plan and execute a Portale Antenati gallery download."""

    def __init__(self, url: str, first: int, last: int | None, descriptive_names: bool = False):
        self.url = url
        self.first = first
        self.last = last
        self.descriptive_names = descriptive_names
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

    def load(self) -> Downloader:
        """Resolve and validate the source manifest without downloading images."""
        if self._manifest is not None:
            return self

        archive_id = None if iiif.is_manifest_url(self.url) else iiif.get_archive_id_from_url(self.url)
        logger.info('Loading manifest from %s', self.url)
        manifest, manifest_url = self._load_manifest()
        all_canvases = iiif.slice_canvases(manifest, 0, None)
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
        """Build a deterministic image plan without image/network writes."""
        self.load()
        if self._plan is not None and self._plan.size == size:
            return self._plan
        assert self._all_canvases is not None
        assert self._canvases is not None

        all_stems = self._build_unique_stems(self._all_canvases)
        selected_stems = all_stems[self.first : self.last]
        items = tuple(
            DownloadItem(canvas=canvas, stem=stem, source_url=iiif.manipulate_image_url(iiif.image_url_for_canvas(canvas), size))
            for canvas, stem in zip(self._canvases, selected_stems, strict=True)
        )
        self._plan = DownloadPlan(items=items, size=size)
        return self._plan

    def _load_manifest(self) -> tuple[dict[str, Any], str]:
        if iiif.is_manifest_url(self.url):
            manifest_url = self.url
        else:
            gallery_reply = http.fetch(self.session, self.url)
            gallery_charset = http.get_content_charset(gallery_reply) or 'utf-8'
            gallery_html = gallery_reply.content.decode(gallery_charset)
            manifest_url = iiif.parse_manifest_url_from_html(gallery_html, self.url)
        logger.debug('Manifest URL: %s', manifest_url)
        manifest_reply = http.fetch(self.session, manifest_url)
        manifest_charset = http.get_content_charset(manifest_reply) or 'utf-8'
        return loads(manifest_reply.content.decode(manifest_charset)), manifest_url

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

    def _build_unique_stems(self, canvases: list[dict[str, Any]]) -> list[str]:
        """Return stable, collision-free output stems for canvases."""
        used: set[str] = set()
        result: list[str] = []
        for index, canvas in enumerate(canvases, start=1):
            label = slugify(str(canvas.get('label', ''))) or f'image-{index}'
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
        """Write the gallery's IIIF metadata to stdout."""
        for entry in self.manifest['metadata']:
            label = entry['label']
            value = entry['value']
            print(f'{label:<25}{value}')
        print(f'{self.gallery_length} images found.')

    def check_dir(self, parentdir: str | None = None, interactive: bool = True) -> None:
        """Ensure the output directory exists, prompting the user on conflict."""
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

    def _thread_main(self, item: DownloadItem, cancel: threading.Event | None) -> int:
        label = slugify(str(item.canvas.get('label', ''))) or item.stem
        temp_name: str | None = None
        try:
            if cancel is not None and cancel.is_set():
                return 0
            http_reply = http.fetch(self.session, item.source_url)
            if cancel is not None and cancel.is_set():
                return 0
            content_type = http.get_content_type(http_reply)
            extension = guess_extension(content_type)
            if not extension:
                raise RuntimeError(f'{item.source_url}: Unable to guess extension "{content_type}"')
            filename = self.dirname / f'{item.stem}{extension}'

            with NamedTemporaryFile(mode='wb', dir=self.dirname, prefix=f'.{item.stem}.', suffix='.tmp', delete=False) as img_file:
                temp_name = img_file.name
                img_file.write(http_reply.content)
                img_file.flush()
                os.fsync(img_file.fileno())
            if cancel is not None and cancel.is_set():
                return 0
            os.replace(temp_name, filename)
            temp_name = None
            return len(http_reply.content)
        except (RequestException, AntenatiError, OSError, RuntimeError) as ex:
            logger.warning('Image %s failed: %s', label, ex)
            raise ThreadError(label) from ex
        finally:
            if temp_name is not None:
                with suppress(FileNotFoundError):
                    os.unlink(temp_name)

    def run(self, n_workers: int, size: int, progress: ProgressBar, cancel: threading.Event | None = None) -> DownloadReport:
        """Execute the selected plan and return a structured outcome report."""
        plan = self.plan(size)
        progress.set_total(plan.expected)
        if cancel is not None and cancel.is_set():
            logger.info('Download cancelled before any work was submitted')
            return DownloadReport(plan.expected, 0, 0, 0, (), True, 0)

        attempted = 0
        completed = 0
        bytes_written = 0
        failures: list[PageFailure] = []
        cancelled = False

        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            futures = {executor.submit(self._thread_main, item, cancel) for item in plan.items}
            for future in as_completed(futures):
                if cancel is not None and cancel.is_set():
                    cancelled = True
                    for pending in futures:
                        pending.cancel()
                if future.cancelled():
                    continue
                attempted += 1
                progress.update()
                try:
                    written = future.result()
                except CancelledError:
                    cancelled = True
                except ThreadError as ex:
                    failures.append(PageFailure(ex.label, str(ex.__cause__)))
                else:
                    if written > 0:
                        completed += 1
                        bytes_written += written
                    elif cancel is not None and cancel.is_set():
                        cancelled = True

        return DownloadReport(
            expected=plan.expected,
            attempted=attempted,
            completed=completed,
            skipped=0,
            failed=tuple(failures),
            cancelled=cancelled,
            bytes_written=bytes_written,
        )
