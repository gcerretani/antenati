# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tkinter GUI for the Portale Antenati downloader."""

from __future__ import annotations

import logging
import queue
import tkinter as tk
import tkinter.filedialog as tkfile
import tkinter.font as tkfont
import tkinter.messagebox as tkmsg
import tkinter.ttk as ttk
from pathlib import Path
from webbrowser import open as webopen

from antenati import __contact__, __copyright__, __version__
from antenati.downloader import DEFAULT_N_THREADS, DEFAULT_SIZE
from antenati.formatting import format_bytes
from antenati.gui.progress import TkProgress
from antenati.gui.worker import Cancelled, Done, DownloadParams, DownloadWorker, Failed, Phase, Progress, Tick
from antenati.output import ExistingPolicy

logger = logging.getLogger(__name__)

_POLL_INTERVAL_MS = 100


class App:
    """Top-level Tk window. Owns the worker, progress bar and shared options."""

    def __init__(self, root: tk.Tk, title: str) -> None:
        self._root = root
        self._root.minsize(760, 420)
        self._root.title(title.strip())

        base_font = tkfont.nametofont('TkDefaultFont')
        self._title_font = base_font.copy()
        self._title_font.configure(size=16, weight='bold')
        self._subtitle_font = base_font.copy()
        self._subtitle_font.configure(size=10)

        self._url = tk.StringVar()
        self._size = tk.IntVar(value=DEFAULT_SIZE)
        self._first = tk.IntVar(value=0)
        self._last = tk.StringVar(value='')
        self._n_workers = tk.IntVar(value=DEFAULT_N_THREADS)
        self._descriptive = tk.BooleanVar(value=False)
        self._path = tk.StringVar()
        self._existing = tk.StringVar(value=ExistingPolicy.ASK.value)

        self._menu = tk.Menu(self._root)
        self._root.configure(menu=self._menu)
        self._build_menu()
        self._build_header()
        self._build_entries()
        self._build_footer()

        self._worker = DownloadWorker()
        self._progress: TkProgress | None = None
        self._terminal_received = True

    def _build_menu(self) -> None:
        menu_file = tk.Menu(self._menu, tearoff=0)
        menu_file.add_command(
            label='Portale Antenati Website',
            command=lambda: webopen('https://antenati.cultura.gov.it/'),
        )
        menu_file.add_command(
            label='Project Website',
            command=lambda: webopen(__contact__),
        )
        menu_file.add_separator()
        menu_file.add_command(
            label='About',
            command=self._show_about,
        )
        self._menu.add_cascade(
            label='File',
            menu=menu_file,
        )

    def _build_header(self) -> None:
        header = ttk.Frame(
            self._root,
            padding=(16, 14, 16, 4),
        )
        header.pack(
            side=tk.TOP,
            fill=tk.X,
        )
        ttk.Label(
            header,
            text='Antenati',
            font=self._title_font,
        ).pack(anchor=tk.W)
        ttk.Label(
            header,
            text='Download digitised registers from Portale Antenati',
            font=self._subtitle_font,
        ).pack(anchor=tk.W)

    def _build_entries(self) -> None:
        entry_frame = ttk.Frame(
            self._root,
            padding=(16, 8, 16, 12),
        )
        entry_frame.pack(
            side=tk.TOP,
            fill=tk.BOTH,
            expand=True,
        )
        entry_frame.columnconfigure(1, weight=1)
        entry_frame.columnconfigure(2, weight=1)

        ttk.Label(
            entry_frame,
            text='Gallery or manifest URL',
        ).grid(
            row=0,
            column=0,
            padx=(0, 10),
            pady=6,
            sticky=tk.W,
        )
        ttk.Entry(
            entry_frame,
            textvariable=self._url,
        ).grid(
            row=0,
            column=1,
            columnspan=3,
            pady=6,
            sticky=tk.EW,
        )

        options = ttk.LabelFrame(
            entry_frame,
            text='Download options',
            padding=10,
        )
        options.grid(
            row=1,
            column=0,
            columnspan=4,
            pady=(8, 10),
            sticky=tk.EW,
        )
        options.columnconfigure(2, weight=1)

        ttk.Label(
            options,
            text='Size (px)',
        ).grid(
            row=0,
            column=0,
            sticky=tk.W,
            padx=(0, 8),
            pady=4,
        )
        ttk.Spinbox(
            options,
            textvariable=self._size,
            width=10,
            from_=0,
            to=5000,
            increment=100,
        ).grid(
            row=0,
            column=1,
            sticky=tk.W,
            padx=(0, 10),
            pady=4,
        )
        ttk.Label(
            options,
            text='0 = full resolution',
        ).grid(
            row=0,
            column=2,
            sticky=tk.W,
            pady=4,
        )

        ttk.Label(
            options,
            text='First page',
        ).grid(
            row=1,
            column=0,
            sticky=tk.W,
            padx=(0, 8),
            pady=4,
        )
        ttk.Spinbox(
            options,
            textvariable=self._first,
            width=10,
            from_=0,
            to=100000,
            increment=1,
        ).grid(
            row=1,
            column=1,
            sticky=tk.W,
            padx=(0, 10),
            pady=4,
        )
        ttk.Label(
            options,
            text='Zero-based index',
        ).grid(
            row=1,
            column=2,
            sticky=tk.W,
            pady=4,
        )

        ttk.Label(
            options,
            text='Last page',
        ).grid(
            row=2,
            column=0,
            sticky=tk.W,
            padx=(0, 8),
            pady=4,
        )
        ttk.Entry(
            options,
            textvariable=self._last,
            width=12,
        ).grid(
            row=2,
            column=1,
            sticky=tk.W,
            padx=(0, 10),
            pady=4,
        )
        ttk.Label(
            options,
            text='Exclusive; leave empty for all remaining pages',
        ).grid(
            row=2,
            column=2,
            sticky=tk.W,
            pady=4,
        )

        ttk.Label(
            options,
            text='Workers',
        ).grid(
            row=3,
            column=0,
            sticky=tk.W,
            padx=(0, 8),
            pady=4,
        )
        ttk.Spinbox(
            options,
            textvariable=self._n_workers,
            width=10,
            from_=1,
            to=64,
            increment=1,
        ).grid(
            row=3,
            column=1,
            sticky=tk.W,
            padx=(0, 10),
            pady=4,
        )
        ttk.Label(
            options,
            text='Concurrent image downloads',
        ).grid(
            row=3,
            column=2,
            sticky=tk.W,
            pady=4,
        )

        ttk.Label(
            options,
            text='Filenames',
        ).grid(
            row=4,
            column=0,
            sticky=tk.W,
            padx=(0, 8),
            pady=4,
        )
        ttk.Checkbutton(
            options,
            text='Include archive/image IDs',
            variable=self._descriptive,
        ).grid(
            row=4,
            column=1,
            columnspan=2,
            sticky=tk.W,
            pady=4,
        )

        ttk.Label(
            options,
            text='Existing files',
        ).grid(
            row=5,
            column=0,
            sticky=tk.W,
            padx=(0, 8),
            pady=4,
        )
        ttk.Combobox(
            options,
            textvariable=self._existing,
            values=[policy.value for policy in ExistingPolicy],
            state='readonly',
            width=12,
        ).grid(
            row=5,
            column=1,
            sticky=tk.W,
            padx=(0, 10),
            pady=4,
        )
        ttk.Label(
            options,
            text='Verified resume is recommended when reusing a destination',
        ).grid(
            row=5,
            column=2,
            sticky=tk.W,
            pady=4,
        )

        ttk.Label(
            entry_frame,
            text='Output directory',
        ).grid(
            row=2,
            column=0,
            padx=(0, 10),
            pady=6,
            sticky=tk.W,
        )
        ttk.Entry(
            entry_frame,
            textvariable=self._path,
        ).grid(
            row=2,
            column=1,
            columnspan=2,
            pady=6,
            sticky=tk.EW,
        )
        ttk.Button(
            entry_frame,
            text='Browse…',
            command=self._browse_path,
        ).grid(
            row=2,
            column=3,
            padx=(10, 0),
            pady=6,
        )

        actions = ttk.Frame(entry_frame)
        actions.grid(
            row=3,
            column=0,
            columnspan=4,
            pady=(12, 0),
            sticky=tk.E,
        )
        self._download_button = ttk.Button(
            actions,
            text='Download',
            command=self._on_download,
        )
        self._download_button.pack(
            side=tk.LEFT,
            padx=4,
        )
        self._cancel_button = ttk.Button(
            actions,
            text='Cancel',
            command=self._on_cancel,
            state=tk.DISABLED,
        )
        self._cancel_button.pack(
            side=tk.LEFT,
            padx=4,
        )
        ttk.Button(
            actions,
            text='Support this project',
            command=lambda: webopen('https://ko-fi.com/gcerretani'),
        ).pack(
            side=tk.LEFT,
            padx=4,
        )

    def _build_footer(self) -> None:
        footer = ttk.Frame(
            self._root,
            padding=(16, 0, 16, 14),
        )
        footer.pack(
            side=tk.BOTTOM,
            fill=tk.X,
        )
        ttk.Separator(
            footer,
            orient=tk.HORIZONTAL,
        ).pack(
            fill=tk.X,
            pady=(0, 8),
        )
        self._footer_label = ttk.Label(
            footer,
            text='Ready',
            anchor=tk.W,
        )
        self._footer_label.pack(
            fill=tk.X,
            pady=(0, 6),
        )
        self._progress_bar = ttk.Progressbar(
            footer,
            mode='determinate',
            orient=tk.HORIZONTAL,
        )
        self._progress_bar.pack(fill=tk.X)

    def _show_about(self) -> None:
        msg = 'antenati: a tool to download data from the Portale Antenati\n'
        msg += f'{__version__}\n'
        msg += f'{__copyright__}'
        tkmsg.showinfo('About', msg)

    def _browse_path(self) -> None:
        selected_path = tkfile.askdirectory()
        if selected_path:
            self._path.set(selected_path)

    def _resolve_gui_policy(self, output: str, policy: ExistingPolicy) -> ExistingPolicy | None:
        if policy is not ExistingPolicy.ASK:
            return policy
        directory = Path(output)
        if not directory.exists() or not directory.is_dir() or not any(directory.iterdir()):
            return ExistingPolicy.ERROR

        resume = tkmsg.askyesnocancel(
            'Existing output',
            'The destination already contains files.\n\nYes: resume and verify existing downloads (recommended)\nNo: choose another action\nCancel: stop',
        )
        if resume is None:
            return None
        if resume:
            return ExistingPolicy.RESUME

        overwrite = tkmsg.askyesnocancel(
            'Existing output',
            'Overwrite planned files?\n\nYes: overwrite\nNo: skip verified files and refuse ambiguous files\nCancel: stop',
        )
        if overwrite is None:
            return None
        return ExistingPolicy.OVERWRITE if overwrite else ExistingPolicy.SKIP

    def _on_download(self) -> None:
        url = self._url.get().strip()
        if not url:
            raise RuntimeError('Please enter a valid URL.')
        output_value = self._path.get().strip()
        if not output_value:
            raise RuntimeError('Please choose an output directory.')

        policy = self._resolve_gui_policy(
            output_value,
            ExistingPolicy(self._existing.get()),
        )
        if policy is None:
            return

        last_raw = self._last.get().strip()
        last_val = int(last_raw) if last_raw else None
        params = DownloadParams(
            url=url,
            output_dir=output_value,
            size=self._size.get(),
            first=int(self._first.get()),
            last=last_val,
            n_workers=int(self._n_workers.get()),
            descriptive_names=bool(self._descriptive.get()),
            existing_policy=policy,
        )

        self._progress = TkProgress(self._progress_bar)
        self._progress.start_indeterminate()
        self._footer_label.configure(text='Loading register metadata…')
        self._terminal_received = False
        self._set_running(True)
        self._worker.start(params)
        self._root.after(
            _POLL_INTERVAL_MS,
            self._drain_events,
        )

    def _on_cancel(self) -> None:
        if self._worker.is_running():
            self._footer_label.configure(text='Cancelling…')
            self._worker.cancel()

    def _drain_events(self) -> None:
        try:
            while True:
                event = self._worker.events.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        if not self._terminal_received:
            self._root.after(
                _POLL_INTERVAL_MS,
                self._drain_events,
            )

    def _handle_event(self, event: object) -> None:
        if isinstance(event, Phase):
            self._footer_label.configure(text=event.message)
            if self._progress is not None and self._progress.total == 0:
                self._progress.start_indeterminate()
        elif isinstance(event, Progress):
            if self._progress is not None:
                self._progress.set_total(event.total)
            self._footer_label.configure(text=f'Downloading 0/{event.total} pages…')
        elif isinstance(event, Tick):
            if self._progress is not None:
                self._progress.update()
                self._footer_label.configure(text=f'Downloading {event.completed}/{self._progress.total} pages…')
        elif isinstance(event, Done):
            self._terminal_received = True
            self._set_running(False)
            report = event.report
            if report.successful:
                self._footer_label.configure(text='Download complete')
                tkmsg.showinfo(
                    'Download complete',
                    f'Downloaded {report.completed}, reused {report.skipped}. New data: {format_bytes(report.bytes_written)}',
                )
            else:
                self._footer_label.configure(text='Download incomplete')
                details = '\n'.join(f'{failure.label}: {failure.reason}' for failure in report.failed)
                tkmsg.showwarning(
                    'Incomplete download',
                    f'Completed {report.completed}/{report.expected}; failed {len(report.failed)}.\n{details}',
                )
        elif isinstance(event, Cancelled):
            self._terminal_received = True
            self._set_running(False)
            self._footer_label.configure(text='Download cancelled')
            tkmsg.showinfo(
                'Cancelled',
                f'Download cancelled after {event.report.completed}/{event.report.expected} pages.',
            )
        elif isinstance(event, Failed):
            self._terminal_received = True
            self._set_running(False)
            self._footer_label.configure(text='Download failed')
            tkmsg.showerror('Error', event.message)

    def _set_running(self, running: bool) -> None:
        self._download_button.configure(
            state=tk.DISABLED if running else tk.NORMAL,
        )
        self._cancel_button.configure(
            state=tk.NORMAL if running else tk.DISABLED,
        )
        if not running and self._progress is not None:
            self._progress.reset()
            self._progress = None


def main() -> None:
    tk_root = tk.Tk()

    def _callback_exception(_type, ex: BaseException, _traceback):
        tkmsg.showerror('Error', f'{ex}')

    tk_root.report_callback_exception = _callback_exception
    App(tk_root, 'antenati')
    tk_root.mainloop()


if __name__ == '__main__':
    main()
