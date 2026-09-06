#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Command-line entry point for the Portale Antenati downloader."""

from __future__ import annotations

import logging
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from pathlib import Path
from urllib.parse import urlsplit

from humanize import naturalsize
from tqdm import tqdm

from antenati import __copyright__, __version__
from antenati.config import DownloadConfig
from antenati.downloader import DEFAULT_N_THREADS, DEFAULT_SIZE, Downloader, DownloadItem, DownloadReport, ProgressBar
from antenati.output import ExistingPolicy, prepare_output, run_with_policy


def _configure_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity >= 2:
        level = logging.DEBUG
    elif verbosity >= 1:
        level = logging.INFO
    logging.basicConfig(level=level, format='%(levelname)s %(name)s: %(message)s')


def run_cli(downloader: Downloader, n_workers: int, size: int, policy: ExistingPolicy = ExistingPolicy.OVERWRITE) -> DownloadReport:
    with tqdm(unit='img') as progress:
        progress_bar = ProgressBar(progress.reset, progress.update)  # type: ignore[arg-type]
        return run_with_policy(downloader, n_workers=n_workers, size=size, progress=progress_bar, policy=policy)


def _planned_filename(item: DownloadItem) -> str:
    suffix = Path(urlsplit(item.source_url).path).suffix.lower()
    if suffix in {'.jpeg', '.jpe'}:
        suffix = '.jpg'
    if suffix not in {'.jpg', '.png', '.tif', '.tiff', '.webp'}:
        suffix = '.img'
    return f'{item.stem}{suffix}'


def print_preview(downloader: Downloader, size: int) -> None:
    plan = downloader.plan(size)
    print(f'Preview: {plan.expected} images -> {downloader.dirname}')
    for index, item in enumerate(plan.items, start=1):
        canvas_id = str(item.canvas.get('@id', ''))
        label = str(item.canvas.get('label', ''))
        print(f'{index:>5}  {_planned_filename(item)}  {label}  {canvas_id}  {item.source_url}')


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
    parser.add_argument('-d', '--descriptive-names', action='store_true', help='include the archive and image IDs in saved file names')
    parser.add_argument('-o', '--output', type=Path, default=None, help='exact output directory (default: generated archive directory)')
    parser.add_argument(
        '--existing',
        choices=[policy.value for policy in ExistingPolicy],
        default=ExistingPolicy.ERROR.value,
        help='existing-file policy: error, overwrite, skip verified files without replacing unverified ones, or verified resume',
    )
    parser.add_argument('--dry-run', action='store_true', help='show the resolved download plan without downloading image bodies or writing files')
    parser.add_argument('-v', '--version', action='version', version=__version__)
    parser.add_argument('--verbose', action='count', default=0, help='increase logging verbosity (--verbose for INFO, twice for DEBUG)')
    args = parser.parse_args()

    config = DownloadConfig(
        url=args.url,
        output_dir=str(args.output) if args.output is not None else None,
        size=args.size,
        first=args.first,
        last=args.last,
        n_workers=args.nthreads,
        descriptive_names=args.descriptive_names,
        existing_policy=ExistingPolicy(args.existing),
        dry_run=args.dry_run,
    ).validate()
    _configure_logging(args.verbose)
    downloader = Downloader(config.url, config.first, config.last, descriptive_names=config.descriptive_names)
    downloader.load()
    if config.output_dir is not None:
        downloader.dirname = Path(config.output_dir)
    if config.dry_run:
        print_preview(downloader, config.size)
        return
    downloader.print_gallery_info()
    prepare_output(downloader, config.output_dir, config.existing_policy)
    report = run_cli(downloader, config.n_workers, config.size, config.existing_policy)
    _print_report(report)
    if report.cancelled or report.failed or not report.successful:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
