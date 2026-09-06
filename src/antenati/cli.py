#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Command-line entry point for the Portale Antenati downloader."""

from __future__ import annotations

import logging
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser

from humanize import naturalsize
from tqdm import tqdm

from antenati import __copyright__, __version__
from antenati.downloader import DEFAULT_N_THREADS, DEFAULT_SIZE, DownloadReport, Downloader, ProgressBar


def _configure_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity >= 2:
        level = logging.DEBUG
    elif verbosity >= 1:
        level = logging.INFO
    logging.basicConfig(level=level, format='%(levelname)s %(name)s: %(message)s')


def run_cli(downloader: Downloader, n_workers: int, size: int) -> DownloadReport:
    """Run the download with a tqdm progress bar attached."""
    with tqdm(unit='img') as progress:
        progress_bar = ProgressBar(progress.reset, progress.update)  # type: ignore[arg-type]
        return downloader.run(n_workers, size, progress_bar)


def _print_report(report: DownloadReport) -> None:
    print(
        f'Completed: {report.completed}/{report.expected}; skipped: {report.skipped}; '
        f'failed: {len(report.failed)}; bytes written: {naturalsize(report.bytes_written, True)}'
    )
    for failure in report.failed:
        print(f' - {failure.label}: {failure.reason}')


def main() -> None:
    parser = ArgumentParser(
        description='Download data from the Portale Antenati',
        epilog=__copyright__,
        formatter_class=ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument('url', metavar='URL', type=str, help='url of the gallery page or of its IIIF manifest')
    parser.add_argument('-s', '--size', type=int, default=DEFAULT_SIZE, help='image size in pixel (0 means full size)')
    parser.add_argument('-n', '--nthreads', type=int, default=DEFAULT_N_THREADS, help='max n. of threads')
    parser.add_argument('-f', '--first', type=int, default=0, help='first image to download')
    parser.add_argument('-l', '--last', type=int, default=None, help='first image NOT to download')
    parser.add_argument('-d', '--descriptive-names', action='store_true', help='include the archive and image IDs in the saved file names')
    parser.add_argument('-v', '--version', action='version', version=__version__)
    parser.add_argument('--verbose', action='count', default=0, help='increase logging verbosity (--verbose for INFO, twice for DEBUG)')
    args = parser.parse_args()

    _configure_logging(args.verbose)
    downloader = Downloader(args.url, args.first, args.last, descriptive_names=args.descriptive_names)
    downloader.load()
    downloader.print_gallery_info()
    downloader.check_dir()
    report = run_cli(downloader, args.nthreads, args.size)
    _print_report(report)
    if report.cancelled or report.failed or not report.successful:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
