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

from humanize import naturalsize
from tqdm import tqdm

from antenati_downloader import DEFAULT_N_THREADS, DEFAULT_SIZE, Downloader, ProgressBar
from antenati_errors import ThreadError

# Backwards-compatible alias: external scripts and ``antenati_gui`` still
# import ``antenati.AntenatiDownloader``. Removing the alias is a major
# version bump scheduled for a later cleanup PR.
AntenatiDownloader = Downloader

# Keep ProgressBar / ThreadError / DEFAULT_* importable from ``antenati``
# for the same reason. Re-exporting from the module makes the move
# transparent to GUI code and any user scripts.
__all__ = [
    'DEFAULT_N_THREADS',
    'DEFAULT_SIZE',
    'AntenatiDownloader',
    'Downloader',
    'ProgressBar',
    'ThreadError',
    '__version__',
    'run_cli',
]


def run_cli(downloader: Downloader, n_workers: int, size: int) -> int:
    """Run the download with a tqdm progress bar attached."""
    with tqdm(unit='img') as progress:
        progress_bar = ProgressBar(progress.reset, progress.update)  # type: ignore[arg-type]
        return downloader.run(n_workers, size, progress_bar)


def main() -> None:
    parser = ArgumentParser(
        description=__doc__,
        epilog=__copyright__,
        formatter_class=ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument('url', metavar='URL', type=str, help='url of the gallery page')
    parser.add_argument(
        '-s',
        '--size',
        type=int,
        default=DEFAULT_SIZE,
        help='image size in pixel (0 means full size)',
    )
    parser.add_argument(
        '-n',
        '--nthreads',
        type=int,
        default=DEFAULT_N_THREADS,
        help='max n. of threads',
    )
    parser.add_argument(
        '-f',
        '--first',
        type=int,
        default=0,
        help='first image to download',
    )
    parser.add_argument(
        '-l',
        '--last',
        type=int,
        default=None,
        help='first image NOT to download',
    )
    parser.add_argument('-v', '--version', action='version', version=__version__)
    args = parser.parse_args()

    downloader = Downloader(args.url, args.first, args.last)
    downloader.print_gallery_info()
    downloader.check_dir()
    gallery_size = run_cli(downloader, args.nthreads, args.size)
    print(f'Done. Total size: {naturalsize(gallery_size, True)}')


if __name__ == '__main__':
    main()
