#!/usr/bin/env python3
"""
antenati.py: a tool to download data from the Portale Antenati
"""

__author__ = 'Giovanni Cerretani'
__copyright__ = 'Copyright (c) 2022, Giovanni Cerretani'
__license__ = 'MIT License'
__version__ = '5.0'
__contact__ = 'https://gcerretani.github.io/antenati/'

from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from json import loads
from mimetypes import guess_extension
from os import mkdir, path
from pathlib import Path
from sys import exit
from typing import Any, Optional

from click import confirm, echo
from humanize import naturalsize
from requests import Session
from slugify import slugify
from tqdm import tqdm

import antenati_http
import antenati_iiif


@dataclass
class ProgressBar:
    """Progress Bar callbacks"""
    set_total: Callable[[int], None]
    update: Callable[[], None]


class ThreadError(Exception):
    """Container to be used with exception chaining."""
    def __init__(self, label: str):
        self.label = label


DEFAULT_SIZE: int = 0
DEFAULT_N_THREADS: int = 2


class AntenatiDownloader:
    """Downloader class"""

    url: str
    session: Session
    archive_id: str
    manifest: dict[str, Any]
    canvases: list[dict[str, Any]]
    dirname: Path
    gallery_length: int

    def __init__(self, url: str, first: int, last: int):
        self.url = url
        self.session = antenati_http.build_session()
        self.archive_id = antenati_iiif.get_archive_id_from_url(url)
        self.manifest = self.__load_manifest()
        self.canvases = antenati_iiif.slice_canvases(self.manifest, first, last)
        self.dirname = self.__generate_dirname()
        self.gallery_length = len(self.canvases)

    def __load_manifest(self) -> dict[str, Any]:
        """Fetch the gallery page, extract the manifest URL, and load it as JSON."""
        gallery_reply = antenati_http.fetch(self.session, self.url)
        gallery_charset = antenati_http.get_content_charset(gallery_reply)
        gallery_html = gallery_reply.content.decode(gallery_charset)
        manifest_url = antenati_iiif.parse_manifest_url_from_html(gallery_html, self.url)
        manifest_reply = antenati_http.fetch(self.session, manifest_url)
        manifest_charset = antenati_http.get_content_charset(manifest_reply)
        return loads(manifest_reply.content.decode(manifest_charset))

    def __generate_dirname(self) -> Path:
        """Generate directory name from info in IIIF manifest"""
        context = antenati_iiif.get_metadata_value(self.manifest, 'Contesto archivistico')
        year = antenati_iiif.get_metadata_value(self.manifest, 'Titolo')
        typology = antenati_iiif.get_metadata_value(self.manifest, 'Tipologia')
        return Path(slugify(f'{context}-{year}-{typology}-{self.archive_id}'))

    def print_gallery_info(self) -> None:
        """Print IIIF gallery info"""
        for i in self.manifest['metadata']:
            label = i['label']
            value = i['value']
            print(f'{label:<25}{value}')
        print(f'{self.gallery_length} images found.')

    def check_dir(self, parentdir: Optional[str] = None, interactive = True) -> None:
        """Check if directory already exists and chdir to it"""
        if parentdir is not None:
            self.dirname = Path(parentdir) / self.dirname
        print(f'Output directory: {self.dirname}')
        if path.exists(self.dirname):
            msg = f'Directory {self.dirname} already exists.'
            if not interactive:
                raise RuntimeError(msg)
            echo(msg)
            if not confirm('Do you want to proceed?'):
                exit(1)
        else:
            mkdir(self.dirname)

    def __thread_main(self, canvas: dict[str, Any], size: int) -> int:
        """Main function for each thread"""
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
            http_reply_size = len(http_reply.content)
            return http_reply_size
        except Exception as ex:
            raise ThreadError(label) from ex

    @staticmethod
    def __executor(max_workers: int) -> ThreadPoolExecutor:
        """Create ThreadPoolExecutor with max_workers threads"""
        return ThreadPoolExecutor(max_workers=max_workers)

    def run_cli(self, n_workers: int, size: int) -> int:
        """Main function spanning run function in a thread pool, with tqdm progress bar"""
        with tqdm(unit='img') as progress:
            progress_bar = ProgressBar(progress.reset, progress.update)  # type: ignore
            return self.run(n_workers, size, progress_bar)

    def run(self, n_workers: int, size: int, progress: ProgressBar) -> int:
        """Main function spanning run function in a thread pool"""
        with self.__executor(n_workers) as executor:
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


def main() -> None:
    """Main"""

    # Parse arguments
    parser = ArgumentParser(
        description=__doc__,
        epilog=__copyright__,
        formatter_class=ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('url', metavar='URL', type=str, help='url of the gallery page')
    parser.add_argument('-s', '--size', type=int, help='image size in pixel (0 means full size)', default=DEFAULT_SIZE)
    parser.add_argument('-n', '--nthreads', type=int, help='max n. of threads', default=DEFAULT_N_THREADS)
    parser.add_argument('-f', '--first', type=int, help='first image to download', default=0)
    parser.add_argument('-l', '--last', type=int, help='first image NOT to download', default=None)
    parser.add_argument('-v', '--version', action='version', version=__version__)
    args = parser.parse_args()

    # Initialize
    downloader = AntenatiDownloader(args.url, args.first, args.last)

    # Print gallery info
    downloader.print_gallery_info()

    # Check if directory already exists and chdir to it
    downloader.check_dir()

    # Run
    gallery_size = downloader.run_cli(args.nthreads, args.size)

    # Print summary
    print(f'Done. Total size: {naturalsize(gallery_size, True)}')


if __name__ == '__main__':
    main()
