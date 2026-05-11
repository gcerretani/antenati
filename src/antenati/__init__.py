"""antenati: a tool to download data from the Portale Antenati."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

__author__ = 'Giovanni Cerretani'
__copyright__ = 'Copyright (c) 2022, Giovanni Cerretani'
__license__ = 'MIT License'
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

# Backwards-compatible alias for callers (notably any external script and
# the historical ``import antenati; antenati.AntenatiDownloader`` shape).
# Removing the alias is a major version bump scheduled for a later
# cleanup PR.
AntenatiDownloader = Downloader

__all__ = [
    'DEFAULT_N_THREADS',
    'DEFAULT_SIZE',
    'AntenatiDownloader',
    'Downloader',
    'ProgressBar',
    'ThreadError',
    '__author__',
    '__contact__',
    '__copyright__',
    '__license__',
    '__version__',
]
