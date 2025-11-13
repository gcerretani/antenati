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
from email.message import Message
from json import loads
from mimetypes import guess_extension
from os import mkdir, path
from pathlib import Path
from re import findall, search
from typing import Any, Optional

from click import confirm, echo
from humanize import naturalsize
from requests import Response, Session
from requests.utils import default_headers
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from slugify import slugify
from tqdm import tqdm


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
    use_selenium: bool
    archive_id: str
    manifest: dict[str, Any]
    canvases: list[dict[str, Any]]
    dirname: Path
    gallery_length: int

    def __init__(self, url: str, first: int, last: int, use_selenium: bool):
        self.url = url
        self.session = Session()
        self.session.headers = self.__http_headers()
        self.use_selenium = use_selenium
        self.archive_id = self.__get_archive_id()
        self.manifest = self.__get_iiif_manifest()
        self.canvases = self.manifest['sequences'][0]['canvases'][first:last]
        self.dirname = self.__generate_dirname()
        self.gallery_length = len(self.canvases)

    @staticmethod
    def __http_headers():
        """Generate HTTP headers to improve speed and to behave as a browser"""
        # SAN server return 403 if HTTP headers are not properly set.
        # - User-Agent: required
        # - Referer: required
        # - Origin: not required
        # Other headers are set to improve performance.
        headers = default_headers()
        headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'
        headers['Referer'] = 'https://antenati.cultura.gov.it/'
        return headers

    def __get_archive_id(self) -> str:
        """Get numeric archive ID from the URL"""
        archive_id_pattern = findall(r'(\d+)', self.url)
        if len(archive_id_pattern) < 2:
            raise RuntimeError(f'Cannot get archive ID from {self.url}')
        return archive_id_pattern[1]

    @staticmethod
    def __get_content_type(http_reply: Response) -> str:
        """Decode Content-Type header using email module."""
        msg = Message()
        msg['Content-Type'] = http_reply.headers['Content-Type']
        return msg.get_content_type()

    @staticmethod
    def __get_content_charset(http_reply: Response):
        """Decode Content-Type header using email module."""
        msg = Message()
        msg['Content-Type'] = http_reply.headers['Content-Type']
        return msg.get_content_charset()

    def __get(self, url: str) -> Response:
        """Get HTTP reply from URL"""
        http_reply = self.session.get(url)
        http_reply.raise_for_status()
        if http_reply.status_code == 202 and http_reply.headers.get('x-amzn-waf-action') == 'challenge':
            raise RuntimeError(f'{http_reply.url}: AWS WAF challenge cannot be bypassed. See https://github.com/gcerretani/antenati/issues/25 for details.')
        return http_reply
    
    def __get_webpage(self) -> str:
        """Get webpage content from URL using Selenium if needed"""
        if self.use_selenium:
            driver = webdriver.Chrome()
            try:
                driver.get(self.url)
                # Wait for the real page title to appear (not the challenge page)
                WebDriverWait(driver, 30).until(EC.title_is('Portale Antenati'))
                return driver.page_source
            finally:
                driver.quit()
        http_reply = self.__get(self.url)
        charset = self.__get_content_charset(http_reply)
        return http_reply.content.decode(charset)

    def __get_iiif_manifest(self) -> dict[str, Any]:
        """Get IIIF manifest as JSON from Portale Antenati gallery page using Selenium if needed"""
        # Use Selenium to get the HTML content (handles JS and WAF challenges)
        html_content = self.__get_webpage()
        html_lines = html_content.splitlines()
        manifest_line = next((line for line in html_lines if 'manifestId' in line), None)
        if not manifest_line:
            raise RuntimeError(f'No IIIF manifest found at {self.url}')
        manifest_url_pattern = search(r"'([A-Za-z0-9.:/-]*)'", manifest_line)
        if not manifest_url_pattern:
            raise RuntimeError(f'Invalid IIIF manifest line found at {self.url}')
        manifest_url = manifest_url_pattern.group(1)
        # Download the manifest JSON as before (using requests)
        http_reply = self.__get(manifest_url)
        charset = self.__get_content_charset(http_reply)
        return loads(http_reply.content.decode(charset))

    def __get_metadata_content(self, label: str) -> str:
        """Get metadata content of IIIF manifest given its label"""
        try:
            return next((i['value'] for i in self.manifest['metadata'] if i['label'] == label))
        except StopIteration as exc:
            raise RuntimeError(f'Cannot get {label} from manifest') from exc

    def __generate_dirname(self) -> Path:
        """Generate directory name from info in IIIF manifest"""
        context = self.__get_metadata_content('Contesto archivistico')
        year = self.__get_metadata_content('Titolo')
        typology = self.__get_metadata_content('Tipologia')
        return Path(slugify(f'{context}-{year}-{typology}-{self.archive_id}'))

    def print_gallery_info(self) -> None:
        """Print IIIF gallery info"""
        for i in self.manifest['metadata']:
            label = i['label']
            value = i['value']
            echo(f'{label:<25}{value}')
        echo(f'{self.gallery_length} images found.')

    def check_dir(self, parentdir: Optional[str] = None, interactive = True) -> None:
        """Check if directory already exists and chdir to it"""
        if parentdir is not None:
            self.dirname = Path(parentdir) / self.dirname
        echo(f'Output directory: {self.dirname}')
        if path.exists(self.dirname):
            msg = f'Directory {self.dirname} already exists.'
            if not interactive:
                raise RuntimeError(msg)
            echo(msg)
            confirm('Do you want to proceed?', abort=True)
        else:
            mkdir(self.dirname)

    @staticmethod
    def __manipulate_url(url: str, size: int) -> str:
        """Get full size string for IIIF request"""
        # SAN server return 403 on certain IIIF requests:
        # - /full/full/0/ (full image, deprecated)
        # - /full/max/0/ (max size based on height and width declared in IIIF manifest)
        # We use an alternative that seems to work, as of today.
        if size > 0:
            size_str = f'/full/!{size},{size}/0/'
        else:
            size_str = '/full/pct:100/0/'
        return url.replace('/full/full/0/', size_str)

    def __thread_main(self, canvas: dict[str, Any], size: int) -> int:
        """Main function for each thread"""
        label = slugify(canvas['label'])
        try:
            manifest_url: str = canvas['images'][0]['resource']['@id']
            url = self.__manipulate_url(manifest_url, size)
            http_reply = self.__get(url)
            content_type = self.__get_content_type(http_reply)
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
    parser.add_argument('-S', '--selenium', action='store_true', help='use Selenium to fetch pages')
    parser.add_argument('-v', '--version', action='version', version=__version__)
    args = parser.parse_args()

    # Initialize
    downloader = AntenatiDownloader(args.url, args.first, args.last, args.selenium)

    # Print gallery info
    downloader.print_gallery_info()

    # Check if directory already exists and chdir to it
    downloader.check_dir()

    # Run
    gallery_size = downloader.run_cli(args.nthreads, args.size)

    # Print summary
    echo(f'Done. Total size: {naturalsize(gallery_size, True)}')


if __name__ == '__main__':
    main()
