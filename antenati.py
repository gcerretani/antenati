#!/usr/bin/env python3
"""
antenati.py: a tool to download data from the Portale Antenati
"""

__author__ = 'Giovanni Cerretani'
__copyright__ = 'Copyright (c) 2022, Giovanni Cerretani'
__license__ = 'MIT License'
__version__ = '2.3'

from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.message import EmailMessage
from json import loads
from mimetypes import guess_extension
from os import chdir, mkdir, path
from re import findall, search
from typing import Any, Dict, List

from certifi import where
from urllib3 import HTTPResponse, HTTPSConnectionPool, PoolManager, make_headers
from click import echo, confirm
from slugify import slugify
from humanize import naturalsize
from tqdm import tqdm


class AntenatiDownloader:
    """Downloader class"""

    url: str
    archive_id: str
    manifest: Dict[str, Any]
    canvases: List[Dict[str, Any]]
    dirname: str
    gallery_length: int
    gallery_size: int

    def __init__(self, url: str, first: int, last: int):
        self.url = url
        self.archive_id = self.__get_archive_id(self.url)
        self.manifest = self.__get_iiif_manifest(self.url)
        self.canvases = self.manifest['sequences'][0]['canvases'][first:last]
        self.dirname = self.__generate_dirname()
        self.gallery_length = len(self.canvases)
        self.gallery_size = 0

    @staticmethod
    def __http_headers() -> Dict[str, Any]:
        """Generate HTTP headers to improve speed and to behave as a browser"""
        # Default headers to reduce data transfers
        headers = make_headers(
            keep_alive=True,
            accept_encoding=True
        )
        # Update 05/2022:
        # SAN server return 403 if HTTP headers are not properly set.
        # - User-Agent: not required, but was required in the past
        # - Referer: required
        # - Origin: not required
        # Not required headers are kept, in case new filters are added.
        headers['User-Agent'] = 'Mozilla/5.0 (Mobile; rv:97.0) Gecko/97.0 Firefox/97.0'
        headers['Referer'] = 'https://www.antenati.san.beniculturali.it/'
        headers['Origin'] = 'https://www.antenati.san.beniculturali.it'
        return headers

    @staticmethod
    def __get_archive_id(url: str) -> str:
        """Get numeric archive ID from the URL"""
        archive_id_pattern = findall(r'(\d+)', url)
        if not archive_id_pattern or len(archive_id_pattern) < 2:
            raise RuntimeError(f'Cannot get archive ID from {url}')
        return archive_id_pattern[1]

    @staticmethod
    def __parse_header(string):
        """Replacement for cgi.parse_header deprecated since Python 3.11"""
        msg = EmailMessage()
        msg['Content-Type'] = string
        return msg.get_content_type(), msg['Content-Type'].params

    @staticmethod
    def __get_iiif_manifest(url: str) -> Dict[str, Any]:
        """Get IIIF manifest as JSON from Portale Antenati gallery page"""
        pool = PoolManager(
            headers=AntenatiDownloader.__http_headers(),
            cert_reqs='CERT_REQUIRED',
            ca_certs=where()
        )
        http_reply: HTTPResponse = pool.request('GET', url)
        if http_reply.status != 200:
            raise RuntimeError(f'{url}: HTTP error {http_reply.status}')
        content_type = AntenatiDownloader.__parse_header(http_reply.headers['Content-Type'])
        html_content = http_reply.data.decode(content_type[1]['charset']).split('\n')
        manifest_line = next((line for line in html_content if 'manifestId' in line), None)
        if not manifest_line:
            raise RuntimeError(f'No IIIF manifest found at {url}')
        manifest_url_pattern = search(r'\'([A-Za-z0-9.:/-]*)\'', manifest_line)
        if not manifest_url_pattern:
            raise RuntimeError(f'Invalid IIIF manifest line found at {url}')
        manifest_url = manifest_url_pattern.group(1)
        http_reply = pool.request('GET', manifest_url)
        if http_reply.status != 200:
            raise RuntimeError(f'{url}: HTTP error {http_reply.status}')
        content_type = AntenatiDownloader.__parse_header(http_reply.headers['Content-Type'])
        return loads(http_reply.data.decode(content_type[1]['charset']))

    def __get_metadata_content(self, label: str) -> str:
        """Get metadata content of IIIF manifest given its label"""
        try:
            return next((i['value'] for i in self.manifest['metadata'] if i['label'] == label))
        except StopIteration as exc:
            raise RuntimeError(f'Cannot get {label} from manifest') from exc

    def __generate_dirname(self) -> str:
        """Generate directory name from info in IIIF manifest"""
        archive_context = self.__get_metadata_content('Contesto archivistico')
        archive_year = self.__get_metadata_content('Titolo')
        archive_typology = self.__get_metadata_content('Tipologia')
        return slugify(f'{archive_context}-{archive_year}-{archive_typology}-{self.archive_id}')

    def print_gallery_info(self) -> None:
        """Print IIIF gallery info"""
        for i in self.manifest['metadata']:
            label = i['label']
            value = i['value']
            print(f'{label:<25}{value}')
        print(f'{self.gallery_length} images found.')

    def check_dir(self) -> None:
        """Check if directory already exists and chdir to it"""
        print(f'Output directory: {self.dirname}')
        if path.exists(self.dirname):
            echo(f'Directory {self.dirname} already exists.')
            confirm('Do you want to proceed?', abort=True)
        else:
            mkdir(self.dirname)
        chdir(self.dirname)

    @staticmethod
    def __thread_main(pool: HTTPSConnectionPool, canvas: Dict[str, Any]) -> int:
        url = canvas['images'][0]['resource']['@id']
        http_reply: HTTPResponse = pool.request('GET', url)
        if http_reply.status != 200:
            raise RuntimeError(f'{url}: HTTP error {http_reply.status}')
        content_type = AntenatiDownloader.__parse_header(http_reply.headers['Content-Type'])
        extension = guess_extension(content_type[0])
        if not extension:
            raise RuntimeError(f'{url}: Unable to guess extension "{content_type[0]}"')
        label = slugify(canvas['label'])
        filename = f'{label}{extension}'
        with open(filename, 'wb') as img_file:
            img_file.write(http_reply.data)
        http_reply_size = len(http_reply.data)
        return http_reply_size

    @staticmethod
    def __executor(max_workers: int) -> ThreadPoolExecutor:
        return ThreadPoolExecutor(max_workers=max_workers)

    @staticmethod
    def __pool(maxsize: int) -> HTTPSConnectionPool:
        return HTTPSConnectionPool(
            host='iiif-antenati.san.beniculturali.it',
            maxsize=maxsize,
            block=True,
            headers=AntenatiDownloader.__http_headers(),
            cert_reqs='CERT_REQUIRED',
            ca_certs=where()
        )

    @staticmethod
    def __progress(total: int) -> tqdm:
        return tqdm(total=total, unit='img')

    def run(self, n_workers: int, n_connections: int) -> None:
        """Main function spanning run function in a thread pool"""
        with self.__executor(n_workers) as executor, self.__pool(n_connections) as pool:
            future_img = {executor.submit(self.__thread_main, pool, i): i for i in self.canvases}
            with self.__progress(self.gallery_length) as progress:
                for future in as_completed(future_img):
                    progress.update()
                    canvas = future_img[future]
                    label = canvas['label']
                    try:
                        size = future.result()
                    except RuntimeError as exc:
                        progress.write(f'{label} error ({exc})')
                    else:
                        self.gallery_size += size

    def print_summary(self) -> None:
        """Print summary"""
        print(f'Done. Total size: {naturalsize(self.gallery_size)}')


def main() -> None:
    """Main"""

    # Parse arguments
    parser = ArgumentParser(
        description=__doc__,
        epilog=__copyright__,
        formatter_class=ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('url', metavar='URL', type=str, help='url of the gallery page')
    parser.add_argument('-n', '--nthreads', type=int, help='max n. of threads', default=8)
    parser.add_argument('-c', '--nconn', type=int, help='max n. of connections', default=4)
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
    downloader.run(args.nthreads, args.nconn)

    # Print summary
    downloader.print_summary()


if __name__ == '__main__':
    main()
