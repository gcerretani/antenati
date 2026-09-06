# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared download configuration used by CLI and GUI."""

from __future__ import annotations

from dataclasses import dataclass

from antenati.errors import ValidationError
from antenati.output import ExistingPolicy
from antenati.validation import DownloadOptions


@dataclass
class DownloadConfig:
    """Interface-independent user configuration for one gallery run."""

    url: str
    output_dir: str | None = None
    size: int = 0
    first: int = 0
    last: int | None = None
    n_workers: int = 2
    descriptive_names: bool = False
    existing_policy: ExistingPolicy = ExistingPolicy.ERROR
    dry_run: bool = False

    def options(self) -> DownloadOptions:
        return DownloadOptions(first=self.first, last=self.last, size=self.size, n_workers=self.n_workers)

    def validate(self, *, require_output: bool = False) -> DownloadConfig:
        self.options().validate()
        if not self.url.strip():
            raise ValidationError('url must not be empty')
        if require_output and (self.output_dir is None or not self.output_dir.strip()):
            raise ValidationError('output directory must not be empty')
        return self
