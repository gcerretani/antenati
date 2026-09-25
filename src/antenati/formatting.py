# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small presentation-formatting helpers shared by CLI and GUI."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any


class _PlainTextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def format_bytes(value: int) -> str:
    """Format a byte count using IEC binary units."""
    amount = float(value)
    units = ('B', 'KiB', 'MiB', 'GiB', 'TiB')
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f'{amount:.0f} {unit}' if unit == 'B' else f'{amount:.1f} {unit}'
        amount /= 1024
    raise AssertionError('unreachable')


def plain_text(value: object) -> str:
    """Return compact readable text from metadata that may contain HTML."""
    parser = _PlainTextHTMLParser()
    parser.feed(str(value))
    parser.close()
    return ' '.join(''.join(parser.parts).split())


def metadata_rows(manifest: dict[str, Any]) -> list[tuple[str, str]]:
    """Return the manifest's descriptive metadata as cleaned ``(label, value)`` pairs, skipping empty entries."""
    rows: list[tuple[str, str]] = []
    for entry in manifest.get('metadata', []):
        if not isinstance(entry, dict):
            continue
        label = plain_text(entry.get('label', ''))
        value = plain_text(entry.get('value', ''))
        if label or value:
            rows.append((label, value))
    return rows
