# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Core download orchestration for the Portale Antenati."""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
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


class Downloader:
    """Download a Portale Antenati gallery to disk."""

    url: str
    session: Session
    descriptive_names: bool
    manifest: dict[str, Any]
    canvases: list[dict[str, Any]]
    archive_id: str
    ark_id: str
    dirname: Path
    gallery_length: int

    def __init__(self, url: str, first: int, last: int | None, descriptive_names: bool = False):
        self.url = url
        self.session = http.build_session()
        self.descriptive_names = descriptive_names
        archive_id = None if iiif.is_manifest_url(url) else iiif.get_archive_id_from_url(url)
        logger.info('Loading manifest from %s', url)
        self.manifest = self.__load_manifest()
        self.canvases = iiif.slice_canvases(self.manifest, first, last)
        self.archive_id = archive_id if archive_id is not None else iiif.get_archive_id_from_canvases(self.canvases)
        self.ark_id = self.__resolve_ark_id()
        self.dirname = self.__generate_dirname()
        self.gallery_length = len(self.canvases)
        self._download_stems = self.__build_unique_stems()
        logger.info('Manifest loaded: %d canvases selected', self.gallery_length)

    def __load_manifest(self) -> dict[str, Any]:
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
        return loads(manifest_reply.content.decode(manifest_charset))

    def __resolve_ark_id(self) -> str:
        first_canvas_url = str(self.canvases[0].get('@id', ''))
        for candidate in (self.url, first_canvas_url):
            ark = iiif.get_ark_id_from_url(candidate)
            if ark:
                return ark
        return self.archive_id

    def __generate_dirname(self) -> Path:
        context = iiif.get_metadata_value(self.manifest, iiif.META_CONTEXT)
        year = iiif.get_metadata_value(self.manifest, iiif.META_TITLE)
        typology = iiif.get_metadata_value(self.manifest, iiif.META_TYPOLOGY)
        return Path(slugify(f'{context}-{year}-{typology}-{self.archive_id}'))

    def __build_unique_stems(self) -> list[str]:
        """Return stable, collision-free output stems for selected canvases.

        Historical/default filenames remain unchanged unless two canvases
        would otherwise resolve to the same path.  In that exceptional case
        only later duplicates receive ``-2``, ``-3`` ... suffixes.
        """
        used: set[str] = set()
        result: list[str] = []
        for index, canvas in enumerate(self.canvases, start=1):
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
        if parentdir is not None:
            self.dirname = Path(parentdir) / self.dirname
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

    def __thread_main(
        self,
        canvas: dict[str, Any],
        stem: str,
        size: int,
        cancel: threading.Event | None,
    ) -> int:
        label = slugify(str(canvas.get('label', ''))) or stem
        temp_name: str | None = None
        try:
            if cancel is not None and cancel.is_set():
                return 0
            image_url = iiif.image_url_for_canvas(canvas)
            url = iiif.manipulate_image_url(image_url, size)
            http_reply = http.fetch(self.session, url)
            if cancel is not None and cancel.is_set():
                return 0
            content_type = http.get_content_type(http_reply)
            extension = guess_extension(content_type)
            if not extension:
                raise RuntimeError(f'{url}: Unable to guess extension "{content_type}"')
            filename = self.dirname / f'{stem}{extension}'

            # Never write directly to the final path.  A failed write must not
            # truncate a previously valid download, and replacing a symlink
            # path must replace the link itself rather than follow its target.
            with NamedTemporaryFile(
                mode='wb',
                dir=self.dirname,
                prefix=f'.{stem}.',
                suffix='.tmp',
                delete=False,
            ) as img_file:
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
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass

    def run(
        self,
        n_workers: int,
        size: int,
        progress: ProgressBar,
        cancel: threading.Event | None = None,
    ) -> int:
        """Download all canvases concurrently. Returns total bytes written."""
        progress.set_total(self.gallery_length)
        if cancel is not None and cancel.is_set():
            logger.info('Download cancelled before any work was submitted')
            return 0

        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            future_img = {
                executor.submit(self.__thread_main, canvas, stem, size, cancel)
                for canvas, stem in zip(self.canvases, self._download_stems, strict=True)
            }
            gallery_size = 0
            failed: list[tuple[str, str]] = []
            for future in as_completed(future_img):
                if cancel is not None and cancel.is_set():
                    for f in future_img:
                        f.cancel()
                    logger.info('Download cancelled by caller')
                    return gallery_size
                progress.update()
                try:
                    gallery_size += future.result()
                except ThreadError as ex:
                    failed.append((ex.label, str(ex.__cause__)))
            if failed:
                msg = f'Failed to download {len(failed)} images:\n'
                msg += '\n - '.join(f'{label}: {reason}' for label, reason in failed)
                raise RuntimeError(msg)
            return gallery_size
