# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tk-bound progress bar helper."""

from __future__ import annotations

import tkinter.ttk as ttk


class TkProgress:
    """Progress driver supporting loading animation and determinate download state."""

    def __init__(self, progress_bar: ttk.Progressbar) -> None:
        self._progress_bar = progress_bar
        self._total = 0
        self._n = 0

    @property
    def total(self) -> int:
        return self._total

    @property
    def current(self) -> int:
        return self._n

    def start_indeterminate(self) -> None:
        """Show an animated loading state before the total page count is known."""
        self._progress_bar.stop()
        self._progress_bar.configure(mode='indeterminate', maximum=100, value=0)
        self._progress_bar.start(12)

    def set_total(self, total: int) -> None:
        """Switch to determinate mode and record the total number of pages."""
        self._total = total
        self._n = 0
        self._progress_bar.master.after(0, self._begin_determinate, total)

    def update(self) -> None:
        """Increment the determinate progress bar by one page."""
        self._n += 1
        if self._total <= 0:
            return
        self._progress_bar.master.after(0, self._set, self._n)

    def reset(self) -> None:
        """Stop animations and return the widget to an idle determinate state."""
        self._total = 0
        self._n = 0
        self._progress_bar.master.after(0, self._reset_widget)

    def _begin_determinate(self, total: int) -> None:
        self._progress_bar.stop()
        self._progress_bar.configure(mode='determinate', maximum=max(total, 1), value=0)

    def _reset_widget(self) -> None:
        self._progress_bar.stop()
        self._progress_bar.configure(mode='determinate', maximum=100, value=0)

    def _set(self, value: float) -> None:
        self._progress_bar['value'] = value
