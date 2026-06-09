"""Core download orchestration for the Portale Antenati.

The :class:`Downloader` is the main entry point used by both the CLI
(:mod:`antenati.cli`) and the GUI (:mod:`antenati.gui`). It composes the
side-effect free helpers from :mod:`antenati.iiif` with the HTTP session
built in :mod:`antenati.http`, and runs the per-canvas image downloads in
a thread pool.

Keeping this orchestration in its own module makes it possible to embed
the downloader from third-party scripts without depending on the CLI
plumbing (``argparse``, ``click.confirm``, ``tqdm``).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from json import loads
from mimetypes import guess_extension
from os import mkdir, path
from pathlib import Path
from sys import exit as sys_exit
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
    """Callback pair used to drive a progress indicator.

    Both callbacks are invoked from the orchestrating thread, so simple
    in-process counters are fine. GUIs that need to marshal updates onto
    a UI thread should do so inside the ``update`` callback.
    """

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
        # A gallery URL embeds the archive ID: extract it up front so a
        # malformed URL fails before any network round-trip. A manifest
        # URL does not embed it; in that case it is recovered after the
        # fetch from the first canvas @id, the only place the manifest
        # repeats it.
        archive_id = None if iiif.is_manifest_url(url) else iiif.get_archive_id_from_url(url)
        logger.info('Loading manifest from %s', url)
        self.manifest = self.__load_manifest()
        self.canvases = iiif.slice_canvases(self.manifest, first, last)
        self.archive_id = archive_id if archive_id is not None else iiif.get_archive_id_from_canvases(self.canvases)
        self.ark_id = self.__resolve_ark_id()
        self.dirname = self.__generate_dirname()
        self.gallery_length = len(self.canvases)
        logger.info('Manifest loaded: %d canvases selected', self.gallery_length)

    def __load_manifest(self) -> dict[str, Any]:
        if iiif.is_manifest_url(self.url):
            # The manifest endpoint is not behind the AWS WAF, so a user
            # who gets a challenge on the gallery page can copy the "IIIF
            # manifest" link from it and pass that URL directly (issue #25).
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

    def __thread_main(self, canvas: dict[str, Any], size: int) -> int:
        label = slugify(canvas['label'])
        try:
            image_url = iiif.image_url_for_canvas(canvas)
            stem = label
            if self.descriptive_names:
                stem = f'{label}+{self.ark_id}+{iiif.get_image_id_from_url(image_url)}'
            url = iiif.manipulate_image_url(image_url, size)
            http_reply = http.fetch(self.session, url)
            content_type = http.get_content_type(http_reply)
            extension = guess_extension(content_type)
            if not extension:
                raise RuntimeError(f'{url}: Unable to guess extension "{content_type}"')
            filename = self.dirname / f'{stem}{extension}'
            with open(filename, 'wb') as img_file:
                img_file.write(http_reply.content)
            return len(http_reply.content)
        except (RequestException, AntenatiError, OSError, RuntimeError) as ex:
            logger.warning('Image %s failed: %s', label, ex)
            raise ThreadError(label) from ex

    def run(
        self,
        n_workers: int,
        size: int,
        progress: ProgressBar,
        cancel: threading.Event | None = None,
    ) -> int:
        """Download all canvases concurrently. Returns total bytes written.

        Passing ``cancel`` lets a caller (typically the GUI) request early
        termination: when the event is set, futures that have not started
        yet are skipped and the call returns the partial total. Already
        running fetches finish naturally — interrupting an in-flight HTTP
        request requires patching :mod:`requests`, which is more invasive
        than the benefit warrants.
        """
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            future_img = {executor.submit(self.__thread_main, i, size) for i in self.canvases}
            progress.set_total(self.gallery_length)
            gallery_size = 0
            failed: dict[str, str] = {}
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
                    failed[ex.label] = str(ex.__cause__)
                    continue
            if failed:
                msg = f'Failed to download {len(failed)} images:\n'
                msg += '\n - '.join(f'{k}: {v}' for k, v in failed.items())
                raise RuntimeError(msg)
            return gallery_size
