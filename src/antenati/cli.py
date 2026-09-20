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

import typer
from requests import RequestException
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TaskID, TaskProgressColumn, TextColumn, TimeElapsedColumn

from antenati import __copyright__, __version__, cli_json, cli_ui
from antenati.config import DownloadConfig
from antenati.downloader import DEFAULT_N_THREADS, DEFAULT_SIZE, Downloader, DownloadItem, DownloadReport, ProgressBar
from antenati.errors import AntenatiError
from antenati.output import ExistingPolicy, existing_output_requires_decision, output_directory, planned_path, prepare_output, run_with_policy


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

    logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(name)s: %(message)s')
    logging.getLogger('antenati').setLevel(level)
    logging.getLogger('urllib3').setLevel(logging.WARNING)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


def run_cli(
    downloader: Downloader,
    n_workers: int,
    size: int,
    policy: ExistingPolicy = ExistingPolicy.OVERWRITE,
    *,
    show_progress: bool = True,
) -> DownloadReport:
    if not show_progress:
        progress_bar = ProgressBar(set_total=lambda _total: None, update=lambda: None)
        return run_with_policy(downloader, n_workers=n_workers, size=size, progress=progress_bar, policy=policy)

    progress = Progress(
        SpinnerColumn('dots'),
        TextColumn('[progress.description]{task.description}'),
        BarColumn(),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=cli_ui.console,
    )
    task_id: TaskID | None = None

    def set_total(total: int) -> None:
        nonlocal task_id
        if task_id is None:
            progress.start()
            task_id = progress.add_task('Downloading', total=total)
        else:
            progress.update(task_id, total=total)

    def advance() -> None:
        if task_id is not None:
            progress.advance(task_id)

    progress_bar = ProgressBar(set_total=set_total, update=advance)
    try:
        return run_with_policy(downloader, n_workers=n_workers, size=size, progress=progress_bar, policy=policy)
    finally:
        if task_id is not None:
            progress.stop()


def _planned_filename(item: DownloadItem) -> str:
    return planned_path(Path('.'), item).name


def print_preview(downloader: Downloader, size: int, *, detailed: bool = False) -> None:
    plan = downloader.plan(size)
    filenames = [_planned_filename(item) for item in plan.items]
    cli_ui.render_preview(plan, downloader.dirname, filenames, detailed=detailed)


def _resolve_cli_policy(
    downloader: Downloader,
    output: str | Path | None,
    policy: ExistingPolicy,
    *,
    allow_prompt: bool = True,
) -> ExistingPolicy:
    """Resolve the interactive ask policy before entering the downloader core."""
    if policy is not ExistingPolicy.ASK or not existing_output_requires_decision(downloader, output):
        return ExistingPolicy.ERROR if policy is ExistingPolicy.ASK else policy

    directory = output_directory(downloader, output)
    if not allow_prompt:
        raise RuntimeError(f'Output directory already exists and is not empty: {directory}. Choose an explicit --existing policy when using --format json.')

    cli_ui.render_existing_output(directory)
    choices = {item.value for item in (ExistingPolicy.RESUME, ExistingPolicy.OVERWRITE, ExistingPolicy.SKIP)}
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


def _run_wizard(*, show_status: bool = True) -> tuple[DownloadConfig, Downloader | None]:
    if not _is_interactive_terminal():
        raise typer.BadParameter('URL is required outside an interactive terminal.', param_hint='URL')

    cli_ui.render_banner()
    url = typer.prompt('Gallery or manifest URL').strip()
    downloader = Downloader(url, 0, None)
    with cli_ui.loading('Loading register metadata…', enabled=show_status):
        downloader.load()

    cli_ui.render_register(downloader.manifest, downloader.gallery_length)

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
        cli_ui.render_existing_output(directory)
        while True:
            selected = typer.prompt('Policy', default='resume').strip().lower()
            if selected == 'cancel':
                raise typer.Exit(code=1)
            if selected in {ExistingPolicy.RESUME.value, ExistingPolicy.OVERWRITE.value, ExistingPolicy.SKIP.value}:
                existing = ExistingPolicy(selected)
                break
            typer.echo('Choose one of: resume, overwrite, skip, cancel.', err=True)

    if not typer.confirm('Start download?', default=True):
        raise typer.Exit(code=1)

    config = DownloadConfig(
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
    return config, downloader if first == 0 and last is None else None


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
    output_format: Annotated[OutputFormat, typer.Option('--format', help='Output format: text or machine-readable JSON')] = OutputFormat.TEXT,
    version: Annotated[bool | None, typer.Option('-v', '--version', callback=_version_callback, is_eager=True, help='Show version and exit')] = None,
    verbose: Annotated[int, typer.Option('--verbose', count=True, help='Increase logging verbosity; repeat for DEBUG')] = 0,
    debug: Annotated[bool, typer.Option('--debug', help='Enable debug logging and tracebacks')] = False,
) -> None:
    """Download a gallery/register from Portale Antenati."""
    json_mode = output_format is OutputFormat.JSON
    if json_mode and url is None:
        raise typer.BadParameter('URL is required with --format json.', param_hint='URL')

    _configure_logging(verbose, debug)
    debug_logging = debug or verbose >= 2

    try:
        wizard_downloader: Downloader | None = None
        if url is None:
            config, wizard_downloader = _run_wizard(show_status=not debug_logging)
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

        downloader = wizard_downloader or Downloader(config.url, config.first, config.last, descriptive_names=config.descriptive_names)
        if wizard_downloader is None:
            with cli_ui.loading('Loading register metadata…', enabled=not debug_logging and not json_mode):
                downloader.load()
            if not json_mode:
                cli_ui.render_register(downloader.manifest, downloader.gallery_length)

        if config.output_dir is not None:
            downloader.dirname = Path(config.output_dir)

        if config.dry_run:
            if json_mode:
                cli_json.emit(cli_json.plan_payload(downloader, config))
            else:
                print_preview(downloader, config.size, detailed=verbose > 0 or debug)
            return

        policy = _resolve_cli_policy(
            downloader,
            config.output_dir,
            config.existing_policy,
            allow_prompt=not json_mode,
        )
        prepare_output(downloader, config.output_dir, policy)
        if not json_mode:
            cli_ui.render_run_summary(downloader.dirname, size=config.size, workers=config.n_workers, policy=policy)
        report = run_cli(
            downloader,
            config.n_workers,
            config.size,
            policy,
            show_progress=not debug_logging and not json_mode,
        )
    except KeyboardInterrupt:
        cli_ui.render_error('Cancelled by user.')
        raise typer.Exit(code=130) from None
    except (AntenatiError, RequestException, OSError, RuntimeError, ValueError) as exc:
        if debug:
            raise
        cli_ui.render_error(str(exc))
        raise typer.Exit(code=1) from None

    if json_mode:
        cli_json.emit(cli_json.report_payload(downloader, config, policy, report))
    else:
        cli_ui.render_report(report, downloader.dirname)
    if report.cancelled or report.failed or not report.successful:
        raise typer.Exit(code=1)


def main() -> None:
    app(prog_name='antenati')


if __name__ == '__main__':
    main()
