# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Rich terminal presentation for the command-line interface."""

from __future__ import annotations

import re
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from antenati import __version__
from antenati.downloader import DownloadPlan, DownloadReport
from antenati.formatting import format_bytes, plain_text
from antenati.output import ExistingPolicy

console = Console(highlight=False)
error_console = Console(stderr=True, highlight=False)

_URL_RE = re.compile(r'https?://[^\s]+')


def loading(message: str, *, enabled: bool = True) -> AbstractContextManager[Any]:
    """Return a Rich status context when interactive rendering is appropriate."""
    if not enabled or not console.is_terminal:
        return nullcontext()
    return console.status(Text(message, style='cyan'), spinner='dots')


def render_banner() -> None:
    body = Text()
    body.append('Antenati', style='bold cyan')
    body.append(f'  v{__version__}', style='dim')
    body.append('\nPortale Antenati downloader', style='dim')
    console.print(Panel(body, border_style='cyan', padding=(0, 1)))


def _linkified(value: str) -> Text:
    text = Text(value)
    for match in _URL_RE.finditer(value):
        url = match.group(0).rstrip('.,;)')
        if not url:
            continue
        end = match.start() + len(url)
        text.stylize(f'cyan underline link {url}', match.start(), end)
    return text


def render_register(manifest: dict[str, Any], page_count: int) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(no_wrap=True)
    table.add_column(ratio=1)

    for entry in manifest.get('metadata', []):
        if not isinstance(entry, dict):
            continue
        label = plain_text(entry.get('label', ''))
        value = plain_text(entry.get('value', ''))
        if not label and not value:
            continue
        table.add_row(Text(label, style='dim'), _linkified(value))

    console.print(
        Panel(
            table,
            title=Text('Register', style='bold cyan'),
            subtitle=Text(f'{page_count} pages', style='dim'),
            border_style='cyan',
            padding=(0, 1),
        )
    )


def render_existing_output(directory: Path) -> None:
    choices = Table.grid(padding=(0, 2))
    choices.add_column(style='bold')
    choices.add_column()
    choices.add_row('resume', Text('Verify and reuse valid downloads  recommended', style='green'))
    choices.add_row('overwrite', 'Download again and replace planned files')
    choices.add_row('skip', 'Reuse verified files; refuse ambiguous existing files')
    choices.add_row('cancel', 'Stop without changing the directory')

    content = Group(Text(str(directory), style='bold'), Text(''), choices)
    console.print(Panel(content, title='Existing output', border_style='yellow', padding=(0, 1)))


def render_run_summary(directory: Path, *, size: int, workers: int, policy: ExistingPolicy) -> None:
    size_label = 'full resolution' if size == 0 else f'{size}px'
    summary = Table.grid(padding=(0, 1))
    summary.add_row(Text('Output', style='dim'), Text(str(directory)))
    summary.add_row(Text('Download', style='dim'), Text(f'{size_label} · {workers} workers · {policy.value}'))
    console.print(summary)
    console.print()


def render_preview(plan: DownloadPlan, directory: Path, filenames: list[str], *, detailed: bool = False) -> None:
    summary = Table.grid(padding=(0, 2))
    summary.add_row(Text('Output', style='dim'), Text(str(directory)))
    summary.add_row(Text('Pages', style='dim'), Text(str(plan.expected)))
    summary.add_row(Text('Size', style='dim'), Text('full resolution' if plan.size == 0 else f'{plan.size}px'))
    console.print(Panel(summary, title='Download plan', border_style='cyan', padding=(0, 1)))

    table = Table(box=box.SIMPLE_HEAD, show_edge=False)
    table.add_column('#', justify='right', style='dim')
    table.add_column('File', style='bold')
    table.add_column('Label')
    if detailed:
        table.add_column('Canvas / source', overflow='fold')

    for index, (item, filename) in enumerate(zip(plan.items, filenames, strict=True), start=1):
        label = plain_text(item.canvas.get('label', ''))
        row: list[str | Text] = [str(index), filename, label]
        if detailed:
            canvas_id = plain_text(item.canvas.get('@id', ''))
            row.append(f'{canvas_id}\n{item.source_url}')
        table.add_row(*row)

    console.print(table)


def render_report(report: DownloadReport, directory: Path) -> None:
    if report.successful:
        status = Text('✓ Download complete', style='bold green')
        border = 'green'
    elif report.cancelled:
        status = Text('■ Download cancelled', style='bold yellow')
        border = 'yellow'
    else:
        status = Text('! Download incomplete', style='bold red')
        border = 'red'

    stats = Table.grid(padding=(0, 2))
    stats.add_row(Text('Downloaded', style='dim'), Text(str(report.completed)))
    stats.add_row(Text('Reused', style='dim'), Text(str(report.skipped)))
    stats.add_row(Text('Failed', style='dim'), Text(str(len(report.failed))))
    stats.add_row(Text('Written', style='dim'), Text(format_bytes(report.bytes_written)))
    stats.add_row(Text('Output', style='dim'), Text(str(directory)))

    blocks: list[RenderableType] = [status, Text(''), stats]
    if report.failed:
        failures = Table(box=box.SIMPLE, show_header=False, show_edge=False)
        failures.add_column(style='bold red', no_wrap=True)
        failures.add_column(overflow='fold')
        for failure in report.failed:
            failures.add_row(failure.label, failure.reason)
        blocks.extend([Text(''), Text('Failures', style='bold'), failures])

    console.print(Panel(Group(*blocks), border_style=border, padding=(0, 1)))


def render_error(message: str) -> None:
    error_console.print(Text(f'Error: {message}', style='bold red'))
