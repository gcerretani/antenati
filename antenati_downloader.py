"""Core download orchestration for the Portale Antenati.

The :class:`Downloader` is the main entry point used by both the CLI
(:mod:`antenati`) and the GUI (:mod:`antenati_gui`). It composes the
side-effect free helpers from :mod:`antenati_iiif` with the HTTP session
built in :mod:`antenati_http`, and runs the per-canvas image downloads in
a thread pool.

Keeping this orchestration in its own module makes it possible to embed
the downloader from third-party scripts without depending on the CLI
plumbing (``argparse``, ``click.confirm``, ``tqdm``).
"""

from __future__ import annotations

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
from requests import Session
from slugify import slugify

import antenati_http
import antenati_iiif
from antenati_errors import ThreadError

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
    archive_id: str
    manifest: dict[str, Any]
    canvases: list[dict[str, Any]]
    dirname: Path
    gallery_length: int

    def __init__(self, url: str, first: int, last: int | None):
        self.url = url
        self.session = antenati_http.build_session()
        self.archive_id = antenati_iiif.get_archive_id_from_url(url)
        self.manifest = self.__load_manifest()
        self.canvases = antenati_iiif.slice_canvases(self.manifest, first, last)
        self.dirname = self.__generate_dirname()
        self.gallery_length = len(self.canvases)

    def __load_manifest(self) -> dict[str, Any]:
        gallery_reply = antenati_http.fetch(self.session, self.url)
        gallery_charset = antenati_http.get_content_charset(gallery_reply) or 'utf-8'
        gallery_html = gallery_reply.content.decode(gallery_charset)
        manifest_url = antenati_iiif.parse_manifest_url_from_html(gallery_html, self.url)
        manifest_reply = antenati_http.fetch(self.session, manifest_url)
        manifest_charset = antenati_http.get_content_charset(manifest_reply) or 'utf-8'
        return loads(manifest_reply.content.decode(manifest_charset))

    def __generate_dirname(self) -> Path:
        context = antenati_iiif.get_metadata_value(self.manifest, 'Contesto archivistico')
        year = antenati_iiif.get_metadata_value(self.manifest, 'Titolo')
        typology = antenati_iiif.get_metadata_value(self.manifest, 'Tipologia')
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
            image_url = antenati_iiif.image_url_for_canvas(canvas)
            url = antenati_iiif.manipulate_image_url(image_url, size)
            http_reply = antenati_http.fetch(self.session, url)
            content_type = antenati_http.get_content_type(http_reply)
            extension = guess_extension(content_type)
            if not extension:
                raise RuntimeError(f'{url}: Unable to guess extension "{content_type}"')
            filename = self.dirname / f'{label}{extension}'
            with open(filename, 'wb') as img_file:
                img_file.write(http_reply.content)
            return len(http_reply.content)
        except Exception as ex:
            raise ThreadError(label) from ex

    def run(self, n_workers: int, size: int, progress: ProgressBar) -> int:
        """Download all canvases concurrently. Returns total bytes written."""
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            future_img = {executor.submit(self.__thread_main, i, size) for i in self.canvases}
            progress.set_total(self.gallery_length)
            gallery_size = 0
            failed: dict[str, str] = {}
            for future in as_completed(future_img):
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
