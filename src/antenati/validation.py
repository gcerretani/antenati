# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared CLI/GUI/programmatic input validation."""

from __future__ import annotations

from dataclasses import dataclass

from antenati.errors import ValidationError

MAX_WORKERS = 64


@dataclass(frozen=True)
class DownloadOptions:
    """Core execution options shared by every user interface."""

    first: int = 0
    last: int | None = None
    size: int = 0
    n_workers: int = 2

    def validate(self) -> DownloadOptions:
        validate_download_options(self)
        return self


def validate_page_range(first: int, last: int | None) -> None:
    if first < 0:
        raise ValidationError('first must be >= 0')
    if last is not None and last < 0:
        raise ValidationError('last must be >= 0')
    if last is not None and last <= first:
        raise ValidationError('last must be greater than first')


def validate_download_options(options: DownloadOptions) -> None:
    validate_page_range(options.first, options.last)
    if options.size < 0:
        raise ValidationError('size must be >= 0')
    if options.n_workers <= 0:
        raise ValidationError('n_workers must be > 0')
    if options.n_workers > MAX_WORKERS:
        raise ValidationError(f'n_workers must be <= {MAX_WORKERS}')
