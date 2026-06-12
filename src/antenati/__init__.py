# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""antenati: a tool to download data from the Portale Antenati."""

from __future__ import annotations

import warnings
from importlib.metadata import PackageNotFoundError, version

__author__ = 'Giovanni Cerretani'
__copyright__ = 'Copyright (c) 2022, Giovanni Cerretani'
__license__ = 'GPL-3.0-or-later'
__contact__ = 'https://gcerretani.github.io/antenati/'

try:
    __version__ = version(__name__)
except PackageNotFoundError:
    # The package is being executed from a source checkout that hasn't
    # been `pip install`-ed; report a sentinel so tests can still
    # assert the attribute exists without pretending to know the tag.
    __version__ = '0.0.0+local'

from antenati.downloader import (
    DEFAULT_N_THREADS,
    DEFAULT_SIZE,
    Downloader,
    ProgressBar,
)
from antenati.errors import ThreadError

__all__ = [
    'DEFAULT_N_THREADS',
    'DEFAULT_SIZE',
    'Downloader',
    'ProgressBar',
    'ThreadError',
    '__author__',
    '__contact__',
    '__copyright__',
    '__license__',
    '__version__',
]


def __getattr__(name: str) -> object:
    if name == 'AntenatiDownloader':
        warnings.warn(
            'AntenatiDownloader is deprecated and will be removed in v7.0; use antenati.Downloader instead.',
            DeprecationWarning,
            stacklevel=2,
        )
        return Downloader
    raise AttributeError(f"module 'antenati' has no attribute {name!r}")
