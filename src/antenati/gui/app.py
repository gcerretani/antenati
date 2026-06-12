# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tkinter GUI for the Portale Antenati downloader."""

from __future__ import annotations

import logging
import queue
import tkinter as tk
import tkinter.filedialog as tkfile
import tkinter.messagebox as tkmsg
import tkinter.ttk as ttk
from webbrowser import open as webopen

from humanize import naturalsize

from antenati import __contact__, __copyright__, __version__
from antenati.downloader import DEFAULT_SIZE
from antenati.gui.progress import TkProgress
from antenati.gui.worker import (
    Cancelled,
    Done,
    DownloadParams,
    DownloadWorker,
    Failed,
    Progress,
    Tick,
)

logger = logging.getLogger(__name__)

_POLL_INTERVAL_MS = 100


class App:
    """Top-level Tk window. Owns the worker, the progress bar and the layout."""

    def __init__(self, root: tk.Tk, title: str) -> None:
        self._root = root
        self._root.minsize(420, 120)
        self._root.title(title.strip())

        self._url = tk.StringVar()
        self._size = tk.IntVar(value=DEFAULT_SIZE)
        self._first = tk.IntVar(value=0)
        self._last = tk.StringVar(value='')
        self._path = tk.StringVar()

        self._menu = tk.Menu(self._root)
        self._root.configure(menu=self._menu)
        self._build_menu()
        self._build_entries()
        self._build_footer()

        self._worker = DownloadWorker()
        self._progress: TkProgress | None = None

    # --- UI construction --------------------------------------------------

    def _build_menu(self) -> None:
        menu_file = tk.Menu(self._menu, tearoff=0)
        menu_file.add_command(
            label='Portale Antenati Website',
            command=lambda: webopen('https://antenati.cultura.gov.it/'),
        )
        menu_file.add_command(label='Project Website', command=lambda: webopen(__contact__))
        menu_file.add_separator()
        menu_file.add_command(label='About', command=self._show_about)
        self._menu.add_cascade(label='File', menu=menu_file)

    def _build_entries(self) -> None:
        entry_frame = ttk.Frame(self._root)
        entry_frame.pack(side=tk.TOP, fill=tk.X)

        tk.Label(entry_frame, text='Archive or manifest URL').grid(row=0, column=0, padx=10, pady=5, sticky=tk.W)
        ttk.Entry(entry_frame, textvariable=self._url, width=100).grid(row=0, column=1, padx=10, pady=5, columnspan=3, sticky=tk.EW)

        options = ttk.LabelFrame(entry_frame, text='Options')
        options.grid(row=1, column=0, columnspan=4, padx=10, pady=5, sticky=tk.EW)

        tk.Label(options, text='Size (px):').grid(row=0, column=0, sticky=tk.W, padx=6, pady=2)
        ttk.Spinbox(options, textvariable=self._size, width=10, from_=0, to=5000, increment=100).grid(row=0, column=1, sticky=tk.W, padx=6, pady=2)
        tk.Label(options, text='Maximum image size in pixels (0 = full size)').grid(row=0, column=2, sticky=tk.W, padx=6, pady=2)

        tk.Label(options, text='First:').grid(row=1, column=0, sticky=tk.W, padx=6, pady=2)
        ttk.Spinbox(options, textvariable=self._first, width=10, from_=0, to=100000, increment=1).grid(row=1, column=1, sticky=tk.W, padx=6, pady=2)
        tk.Label(options, text='Index (0-based) of the first image to download').grid(row=1, column=2, sticky=tk.W, padx=6, pady=2)

        tk.Label(options, text='Last (exclusive):').grid(row=2, column=0, sticky=tk.W, padx=6, pady=2)
        ttk.Entry(options, textvariable=self._last, width=10).grid(row=2, column=1, sticky=tk.W, padx=6, pady=2)
        tk.Label(options, text='Index NOT to download; leave empty to download all').grid(row=2, column=2, sticky=tk.W, padx=6, pady=2)

        tk.Label(entry_frame, text='Destination folder').grid(row=2, column=0, padx=10, pady=5, sticky=tk.EW)
        ttk.Entry(entry_frame, textvariable=self._path, width=100).grid(row=2, column=1, padx=10, pady=5, columnspan=2, sticky=tk.EW)
        ttk.Button(entry_frame, text='Browse', command=self._browse_path).grid(row=2, column=3, padx=10, pady=5, sticky=tk.EW)

        self._download_button = ttk.Button(entry_frame, text='Download', command=self._on_download)
        self._download_button.grid(row=3, column=1, padx=5, pady=5)
        self._cancel_button = ttk.Button(entry_frame, text='Cancel', command=self._on_cancel, state=tk.DISABLED)
        self._cancel_button.grid(row=3, column=2, padx=5, pady=5)
        ttk.Button(
            entry_frame,
            text='Support this project',
            command=lambda: webopen('https://ko-fi.com/gcerretani'),
        ).grid(row=3, column=3, padx=5, pady=5)

    def _build_footer(self) -> None:
        footer_frame = ttk.Frame(self._root)
        footer_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self._footer_label = ttk.Label(footer_frame, anchor=tk.W)
        self._footer_label.grid(row=0, column=0, padx=2, pady=2, sticky=tk.EW)
        footer_frame.columnconfigure(0, weight=1)
        self._progress_bar = ttk.Progressbar(self._root, mode='determinate', orient=tk.HORIZONTAL)
        self._progress_bar.pack(side=tk.BOTTOM, fill=tk.BOTH, padx=2, pady=2)

    # --- Event handlers ---------------------------------------------------

    def _show_about(self) -> None:
        msg = 'antenati: a tool to download data from the Portale Antenati\n'
        msg += f'{__version__}\n'
        msg += f'{__copyright__}'
        tkmsg.showinfo('About', msg)

    def _browse_path(self) -> None:
        selected_path = tkfile.askdirectory()
        if selected_path:
            self._path.set(selected_path)

    def _on_download(self) -> None:
        url = self._url.get().strip()
        if not url:
            raise RuntimeError('Please enter a valid URL.')
        path_value = self._path.get().strip()
        if not path_value:
            raise RuntimeError('Please enter a valid destination folder.')

        last_raw = self._last.get().strip()
        last_val = int(last_raw) if last_raw else None

        params = DownloadParams(
            url=url,
            parent_dir=path_value,
            size=self._size.get(),
            first=int(self._first.get()),
            last=last_val,
        )

        self._progress = TkProgress(self._progress_bar)
        self._set_running(True)
        self._worker.start(params)
        self._root.after(_POLL_INTERVAL_MS, self._drain_events)

    def _on_cancel(self) -> None:
        if self._worker.is_running():
            self._footer_label.configure(text='Cancelling...')
            self._worker.cancel()

    def _drain_events(self) -> None:
        try:
            while True:
                event = self._worker.events.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        if self._worker.is_running():
            self._root.after(_POLL_INTERVAL_MS, self._drain_events)

    def _handle_event(self, event: object) -> None:
        if isinstance(event, Progress):
            if self._progress is not None:
                self._progress.set_total(event.total)
        elif isinstance(event, Tick):
            if self._progress is not None:
                self._progress.update()
        elif isinstance(event, Done):
            self._set_running(False)
            tkmsg.showinfo(
                'Success',
                f'Operation completed successfully. Total size: {naturalsize(event.total_bytes, True)}',
            )
        elif isinstance(event, Cancelled):
            self._set_running(False)
            tkmsg.showinfo('Cancelled', 'Download cancelled.')
        elif isinstance(event, Failed):
            self._set_running(False)
            tkmsg.showerror('Error', event.message)

    def _set_running(self, running: bool) -> None:
        self._download_button.configure(state=tk.DISABLED if running else tk.NORMAL)
        self._cancel_button.configure(state=tk.NORMAL if running else tk.DISABLED)
        self._footer_label.configure(text='Operation in progress...' if running else '')
        if not running and self._progress is not None:
            self._progress.reset()
            self._progress = None


def main() -> None:
    """Launch the Tkinter GUI."""
    tk_root = tk.Tk()

    def _callback_exception(_type, ex: BaseException, _traceback):
        tkmsg.showerror('Error', f'{ex}')

    tk_root.report_callback_exception = _callback_exception
    App(tk_root, 'antenati')
    tk_root.mainloop()


if __name__ == '__main__':
    main()
