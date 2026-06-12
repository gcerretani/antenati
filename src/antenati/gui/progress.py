# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tk-bound progress bar helper.

``TkProgress`` implements the same two-callable shape as
:class:`antenati.downloader.ProgressBar` so that it can be passed to
:meth:`antenati.downloader.Downloader.run`. The callbacks dispatch the
actual widget mutation onto the main Tk thread via ``after``, because
the underlying ``ttk.Progressbar`` is not safe to touch from a worker
thread.
"""

from __future__ import annotations

import tkinter.ttk as ttk


class TkProgress:
    """Determinate progress bar driver wired to a ``ttk.Progressbar``."""

    def __init__(self, progress_bar: ttk.Progressbar) -> None:
        self._progress_bar = progress_bar
        self._total = 0
        self._n = 0

    def set_total(self, total: int) -> None:
        """Record the total number of items the bar will receive."""
        self._total = total
        self._n = 0
        self._progress_bar.master.after(0, self._set, 0)

    def update(self) -> None:
        """Increment the bar by one item."""
        self._n += 1
        if self._total <= 0:
            return
        percent = 100 * self._n / self._total
        self._progress_bar.master.after(0, self._set, percent)

    def reset(self) -> None:
        """Send the bar back to zero (e.g. after cancel)."""
        self._total = 0
        self._n = 0
        self._progress_bar.master.after(0, self._set, 0)

    def _set(self, value: float) -> None:
        self._progress_bar['value'] = value
