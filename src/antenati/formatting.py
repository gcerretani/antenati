# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small presentation-formatting helpers shared by CLI and GUI."""

from __future__ import annotations


def format_bytes(value: int) -> str:
    """Format a byte count using IEC binary units."""
    amount = float(value)
    units = ('B', 'KiB', 'MiB', 'GiB', 'TiB')
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f'{amount:.0f} {unit}' if unit == 'B' else f'{amount:.1f} {unit}'
        amount /= 1024
    raise AssertionError('unreachable')
