#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Command-line entry point for the Portale Antenati downloader."""

from __future__ import annotations

import logging
import sys
from enum import Enum
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

import typer
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn

from antenati import __copyright__, __version__
from antenati.config import DownloadConfig
from antenati.downloader import DEFAULT_N_THREADS, DEFAULT_SIZE, Downloader, DownloadItem, DownloadReport, ProgressBar
from antenati.formatting import format_bytes
from antenati.output import ExistingPolicy, existing_output_requires_decision, output_directory, prepare_output, run_with_policy


class OutputFormat(str, Enum):
    """CLI output formats."""

    TEXT = 'text'
    JSON = 'json'


app = typer.Typer(
    add_completion=False,
    help='Download data from the Portale Antenati.',
    epilog=__copyright__,
    no_args_is_help=False,
    rich_markup_mode='rich',
)


def _configure_logging(verbosity: int, debug: bool = False) -> None:
    level = logging.WARNING
    if debug or verbosity >= 2:
        level = logging.DEBUG
    elif verbosity >= 1:
        level = logging.INFO
    logging.basicConfig(level=level, format='%(levelname)s %(name)s: %(message)s')


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


def run_cli(downloader: Downloader, n_workers: int, size: int, policy: ExistingPolicy = ExistingPolicy.OVERWRITE) -> DownloadReport:
    with Progress(
        TextColumn('[progress.description]{task.description}'),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn('{task.completed:.0f}/{task.total:.0f}'),
    ) as progress:
        task_id = progress.add_task('Downloading', total=0)

        def set_total(total: int) -> None:
            progress.update(task_id, total=total)

        def advance() -> None:
            progress.advance(task_id)

        progress_bar = ProgressBar(set_total=set_total, update=advance)
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


def _resolve_cli_policy(downloader: Downloader, output: str | Path | None, policy: ExistingPolicy) -> ExistingPolicy:
    """Resolve the interactive ask policy before entering the downloader core."""
    if policy is not ExistingPolicy.ASK or not existing_output_requires_decision(downloader, output):
        return ExistingPolicy.ERROR if policy is ExistingPolicy.ASK else policy

    directory = output_directory(downloader, output)
    typer.echo(f'Output directory already exists and is not empty: {directory}')
    typer.echo('Choose how to handle existing files:')
    typer.echo('  resume    verify and reuse valid downloads (recommended)')
    typer.echo('  overwrite download again and replace planned files')
    typer.echo('  skip      reuse verified files; refuse ambiguous existing files')
    typer.echo('  cancel    stop without changing the directory')
    choices = {policy.value for policy in (ExistingPolicy.RESUME, ExistingPolicy.OVERWRITE, ExistingPolicy.SKIP)}
    while True:
        selected = typer.prompt('Policy', default='resume', show_default=True).strip().lower()
        if selected == 'cancel':
            raise typer.Exit(code=1)
        if selected in choices:
            return ExistingPolicy(selected)
        typer.echo('Choose one of: resume, overwrite, skip, cancel.', err=True)


def _is_interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _prompt_int(label: str, default: int, *, minimum: int = 0) -> int:
    while True:
        value = typer.prompt(label, default=default, type=int)
        if value >= minimum:
            return value
        typer.echo(f'Value must be >= {minimum}.', err=True)


def _run_wizard() -> DownloadConfig:
    if not _is_interactive_terminal():
        raise typer.UsageError('Missing argument URL. Run with --help for usage.')

    typer.echo()
    typer.echo('Antenati interactive setup')
    typer.echo()

    url = typer.prompt('Gallery or manifest URL').strip()
    downloader = Downloader(url, 0, None)
    downloader.load()

    typer.echo()
    downloader.print_gallery_info()
    typer.echo()

    selection = typer.prompt('Pages [all/range]', default='all').strip().lower()
    if selection == 'range':
        first = _prompt_int('First image (0-based)', 0)
        last_value = _prompt_int('Last image (exclusive)', downloader.gallery_length, minimum=first + 1)
        last: int | None = last_value
    else:
        first = 0
        last = None

    size_choice = typer.prompt('Image size [full/3000/2000/1000/custom]', default='full').strip().lower()
    if size_choice == 'full':
        size = 0
    elif size_choice in {'3000', '2000', '1000'}:
        size = int(size_choice)
    elif size_choice == 'custom':
        size = _prompt_int('Image size in pixels', 2000, minimum=1)
    else:
        raise typer.BadParameter('Choose full, 3000, 2000, 1000, or custom.', param_hint='image size')

    default_output = str(downloader.dirname)
    output_text = typer.prompt('Output directory', default=default_output).strip()
    output_dir = output_text or default_output

    existing = ExistingPolicy.ASK
    directory = Path(output_dir)
    if directory.exists() and directory.is_dir() and any(directory.iterdir()):
        typer.echo()
        typer.echo('Output directory already exists and is not empty.')
        typer.echo('  resume    verify and reuse valid downloads (recommended)')
        typer.echo('  overwrite download again and replace planned files')
        typer.echo('  skip      reuse verified files; refuse ambiguous existing files')
        typer.echo('  cancel    stop')
        while True:
            selected = typer.prompt('Policy', default='resume').strip().lower()
            if selected == 'cancel':
                raise typer.Exit(code=1)
            if selected in {ExistingPolicy.RESUME.value, ExistingPolicy.OVERWRITE.value, ExistingPolicy.SKIP.value}:
                existing = ExistingPolicy(selected)
                break
            typer.echo('Choose one of: resume, overwrite, skip, cancel.', err=True)

    typer.echo()
    if not typer.confirm('Start download?', default=True):
        raise typer.Exit(code=1)

    return DownloadConfig(
        url=url,
        output_dir=output_dir,
        size=size,
        first=first,
        last=last,
        n_workers=DEFAULT_N_THREADS,
        descriptive_names=False,
        existing_policy=existing,
        dry_run=False,
    ).validate()


def _print_report(report: DownloadReport) -> None:
    print(
        f'Completed: {report.completed}/{report.expected}; skipped: {report.skipped}; '
        f'failed: {len(report.failed)}; bytes written: {format_bytes(report.bytes_written)}'
    )
    for failure in report.failed:
        print(f' - {failure.label}: {failure.reason}')


@app.command()
def cli(
    url: Annotated[str | None, typer.Argument(help='URL of the gallery page or its IIIF manifest')] = None,
    size: Annotated[int, typer.Option('-s', '--size', help='Image size in pixels; 0 means full size')] = DEFAULT_SIZE,
    workers: Annotated[int, typer.Option('-n', '--workers', '--nthreads', help='Maximum number of concurrent download workers')] = DEFAULT_N_THREADS,
    first: Annotated[int, typer.Option('-f', '--first', help='First image to download')] = 0,
    last: Annotated[int | None, typer.Option('-l', '--last', help='First image NOT to download')] = None,
    descriptive_names: Annotated[bool, typer.Option('-d', '--descriptive-names', help='Include archive and image IDs in saved file names')] = False,
    output: Annotated[Path | None, typer.Option('-o', '--output', help='Exact output directory (default: generated archive directory)')] = None,
    existing: Annotated[ExistingPolicy, typer.Option('--existing', help='How to handle an existing output directory')] = ExistingPolicy.ASK,
    dry_run: Annotated[bool, typer.Option('--dry-run', help='Show the resolved download plan without writing image files')] = False,
    output_format: Annotated[OutputFormat, typer.Option('--format', help='Output format; JSON rendering will land later in #79')] = OutputFormat.TEXT,
    version: Annotated[bool | None, typer.Option('-v', '--version', callback=_version_callback, is_eager=True, help='Show version and exit')] = None,
    verbose: Annotated[int, typer.Option('--verbose', count=True, help='Increase logging verbosity; repeat for DEBUG')] = 0,
    debug: Annotated[bool, typer.Option('--debug', help='Enable debug logging')] = False,
) -> None:
    """Download a gallery/register from Portale Antenati."""
    if output_format is OutputFormat.JSON:
        raise typer.BadParameter('JSON output is scaffolded but not implemented yet in this draft', param_hint='--format')

    if url is None:
        config = _run_wizard()
    else:
        config = DownloadConfig(
            url=url,
            output_dir=str(output) if output is not None else None,
            size=size,
            first=first,
            last=last,
            n_workers=workers,
            descriptive_names=descriptive_names,
            existing_policy=existing,
            dry_run=dry_run,
        ).validate()
    _configure_logging(verbose, debug)
    downloader = Downloader(config.url, config.first, config.last, descriptive_names=config.descriptive_names)
    downloader.load()
    if config.output_dir is not None:
        downloader.dirname = Path(config.output_dir)
    if config.dry_run:
        print_preview(downloader, config.size)
        return
    downloader.print_gallery_info()
    policy = _resolve_cli_policy(downloader, config.output_dir, config.existing_policy)
    prepare_output(downloader, config.output_dir, policy)
    report = run_cli(downloader, config.n_workers, config.size, policy)
    _print_report(report)
    if report.cancelled or report.failed or not report.successful:
        raise typer.Exit(code=1)


def main() -> None:
    app(prog_name='antenati')


if __name__ == '__main__':
    main()
