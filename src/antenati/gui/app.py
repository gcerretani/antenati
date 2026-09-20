# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tkinter GUI for the Portale Antenati downloader."""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
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
from antenati.gui.worker import (
    Cancelled,
    Destination,
    Done,
    DownloadParams,
    DownloadWorker,
    ExistingOutput,
    Failed,
    Phase,
    Progress,
    Tick,
)
from antenati.output import ExistingPolicy

logger = logging.getLogger(__name__)

_POLL_INTERVAL_MS = 100


class App:
    """Top-level Tk window. Owns the worker, progress bar and shared options."""

    def __init__(self, root: tk.Tk, title: str) -> None:
        self._root = root
        self._root.minsize(760, 450)
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
        self._base_path = tk.StringVar(value=str(Path.cwd().resolve()))
        self._automatic_output = tk.BooleanVar(value=True)
        self._register_folder = tk.StringVar(value='Will be determined from metadata')
        self._resolved_output: Path | None = None
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

        destination = ttk.LabelFrame(
            entry_frame,
            text='Destination',
            padding=10,
        )
        destination.grid(
            row=2,
            column=0,
            columnspan=4,
            pady=(0, 10),
            sticky=tk.EW,
        )
        destination.columnconfigure(1, weight=1)

        ttk.Label(
            destination,
            text='Save in',
        ).grid(
            row=0,
            column=0,
            padx=(0, 10),
            pady=4,
            sticky=tk.W,
        )
        ttk.Entry(
            destination,
            textvariable=self._base_path,
            state='readonly',
        ).grid(
            row=0,
            column=1,
            pady=4,
            sticky=tk.EW,
        )
        ttk.Button(
            destination,
            text='Change…',
            command=self._browse_path,
        ).grid(
            row=0,
            column=2,
            padx=(10, 0),
            pady=4,
        )
        ttk.Checkbutton(
            destination,
            text='Create a separate folder for each register (recommended)',
            variable=self._automatic_output,
            command=self._refresh_destination_mode,
        ).grid(
            row=1,
            column=1,
            columnspan=2,
            pady=(4, 2),
            sticky=tk.W,
        )
        ttk.Label(
            destination,
            text='Register folder',
        ).grid(
            row=2,
            column=0,
            padx=(0, 10),
            pady=(2, 4),
            sticky=tk.W,
        )
        ttk.Entry(
            destination,
            textvariable=self._register_folder,
            state='readonly',
            width=48,
        ).grid(
            row=2,
            column=1,
            columnspan=2,
            pady=(2, 4),
            sticky=tk.EW,
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
        progress_row = ttk.Frame(footer)
        progress_row.pack(fill=tk.X)
        self._progress_bar = ttk.Progressbar(
            progress_row,
            mode='determinate',
            orient=tk.HORIZONTAL,
        )
        self._progress_bar.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
        )
        self._open_folder_button = ttk.Button(
            progress_row,
            text='Open folder',
            command=self._open_output_folder,
            state=tk.DISABLED,
        )
        self._open_folder_button.pack(
            side=tk.LEFT,
            padx=(10, 0),
        )

    def _show_about(self) -> None:
        msg = 'antenati: a tool to download data from the Portale Antenati\n'
        msg += f'{__version__}\n'
        msg += f'{__copyright__}'
        tkmsg.showinfo('About', msg)

    def _browse_path(self) -> None:
        selected_path = tkfile.askdirectory(initialdir=self._base_path.get())
        if selected_path:
            self._base_path.set(str(Path(selected_path).resolve()))
            self._resolved_output = None
            self._open_folder_button.configure(state=tk.DISABLED)
            self._refresh_destination_mode()

    def _refresh_destination_mode(self) -> None:
        self._resolved_output = None
        self._open_folder_button.configure(state=tk.DISABLED)
        if self._automatic_output.get():
            self._register_folder.set('Will be determined from metadata')
        else:
            self._register_folder.set('(same as Save in)')

    def _open_output_folder(self) -> None:
        directory = self._resolved_output
        if directory is None or not directory.is_dir():
            tkmsg.showwarning('Folder unavailable', 'The destination folder does not exist yet.')
            return
        if sys.platform == 'win32':
            os.startfile(directory)  # type: ignore[attr-defined]
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', str(directory)])
        else:
            subprocess.Popen(['xdg-open', str(directory)])

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
        base_path = self._base_path.get().strip()
        automatic_output = bool(self._automatic_output.get())
        self._resolved_output = None
        self._open_folder_button.configure(state=tk.DISABLED)
        self._register_folder.set('Resolving…' if automatic_output else '(same as Save in)')

        last_raw = self._last.get().strip()
        last_val = int(last_raw) if last_raw else None
        params = DownloadParams(
            url=url,
            output_dir=None if automatic_output else base_path,
            output_base_dir=base_path,
            automatic_output=automatic_output,
            size=self._size.get(),
            first=int(self._first.get()),
            last=last_val,
            n_workers=int(self._n_workers.get()),
            descriptive_names=bool(self._descriptive.get()),
            existing_policy=ExistingPolicy(self._existing.get()),
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
        if isinstance(event, Destination):
            self._resolved_output = Path(event.path)
            if self._automatic_output.get():
                self._register_folder.set(self._resolved_output.name)
            else:
                self._register_folder.set('(same as Save in)')
        elif isinstance(event, ExistingOutput):
            policy = self._resolve_gui_policy(event.path, ExistingPolicy.ASK)
            if policy is None:
                self._footer_label.configure(text='Cancelling…')
                self._worker.cancel()
            else:
                self._worker.resolve_existing_policy(policy)
        elif isinstance(event, Phase):
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
            output = str(self._resolved_output) if self._resolved_output is not None else self._base_path.get()
            if report.successful:
                self._footer_label.configure(text='Download complete')
                self._open_folder_button.configure(state=tk.NORMAL)
                tkmsg.showinfo(
                    'Download complete',
                    f'Downloaded {report.completed}, reused {report.skipped}. New data: {format_bytes(report.bytes_written)}\n\nSaved to:\n{output}',
                )
            else:
                self._footer_label.configure(text='Download incomplete')
                if self._resolved_output is not None and self._resolved_output.is_dir():
                    self._open_folder_button.configure(state=tk.NORMAL)
                details = '\n'.join(f'{failure.label}: {failure.reason}' for failure in report.failed)
                tkmsg.showwarning(
                    'Incomplete download',
                    f'Completed {report.completed}/{report.expected}; failed {len(report.failed)}.\n{details}',
                )
        elif isinstance(event, Cancelled):
            self._terminal_received = True
            self._set_running(False)
            output = str(self._resolved_output) if self._resolved_output is not None else self._base_path.get()
            self._footer_label.configure(text='Download cancelled')
            if self._resolved_output is not None and self._resolved_output.is_dir():
                self._open_folder_button.configure(state=tk.NORMAL)
            tkmsg.showinfo(
                'Cancelled',
                f'Download cancelled after {event.report.completed}/{event.report.expected} pages.',
            )
        elif isinstance(event, Failed):
            self._terminal_received = True
            self._set_running(False)
            self._footer_label.configure(text='Download failed')
            if self._resolved_output is not None and self._resolved_output.is_dir():
                self._open_folder_button.configure(state=tk.NORMAL)
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
