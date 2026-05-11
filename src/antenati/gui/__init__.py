"""Tkinter GUI package for the Portale Antenati downloader.

The Tk import is deferred to :func:`main` so that importing the worker
or progress sub-modules from a tk-less environment (CI, unit tests)
doesn't fail.
"""

from __future__ import annotations

__all__ = ['main']


def main() -> None:
    """Launch the Tkinter GUI. Imported lazily to keep Tk optional."""
    from antenati.gui.app import main as _app_main

    _app_main()
