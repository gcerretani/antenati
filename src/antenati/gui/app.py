# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tkinter GUI for the Portale Antenati downloader."""

from __future__ import annotations

import functools
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

from antenati import __contact__, __copyright__, __support__, __version__
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
    PreviewFailed,
    PreviewLoader,
    Progress,
    RegisterPreview,
    Tick,
)
from antenati.i18n import _
from antenati.output import ExistingPolicy

logger = logging.getLogger(__name__)

_POLL_INTERVAL_MS = 100
_CUSTOM_SIZE_DEFAULT = 2000
# The register panel has a fixed width and never requests height, so loading
# metadata cannot resize the window; it stretches to the options column height.
_REGISTER_PANEL_WIDTH = 400
_REGISTER_WRAP_PX = 370
_LINK_COLOR = '#0645ad'
_ERROR_COLOR = '#b00020'
_MUTED_COLOR = '#5f6368'


def _open_link(url: str, _event: object = None) -> None:
    webopen(url)


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
        self._caption_font = base_font.copy()
        self._caption_font.configure(size=max(7, abs(base_font.actual('size')) - 1))

        self._url = tk.StringVar()
        self._max_size = tk.BooleanVar(value=DEFAULT_SIZE == 0)
        self._size = tk.IntVar(value=DEFAULT_SIZE or _CUSTOM_SIZE_DEFAULT)
        self._first = tk.IntVar(value=0)
        self._last = tk.StringVar(value='')
        self._n_workers = tk.IntVar(value=DEFAULT_N_THREADS)
        self._descriptive = tk.BooleanVar(value=False)
        self._base_path = tk.StringVar(value=str(Path.cwd().resolve()))
        self._automatic_output = tk.BooleanVar(value=True)
        self._register_folder = tk.StringVar(value=_('Will be determined from metadata'))
        self._resolved_output: Path | None = None
        self._existing = tk.StringVar(value=ExistingPolicy.ASK.value)
        self._preview = PreviewLoader()
        self._preview_url = ''
        self._preview_dirname: str | None = None
        self._preview_pending = False

        self._menu = tk.Menu(self._root)
        self._root.configure(menu=self._menu)
        self._build_menu()
        self._build_header()
        self._build_entries()
        self._build_footer()
        self._refresh_size_mode()

        self._worker = DownloadWorker()
        self._progress: TkProgress | None = None
        self._terminal_received = True

    def _build_menu(self) -> None:
        menu_file = tk.Menu(self._menu, tearoff=0)
        menu_file.add_command(
            label=_('Portale Antenati Website'),
            command=lambda: webopen('https://antenati.cultura.gov.it/'),
        )
        menu_file.add_command(
            label=_('Project Website'),
            command=lambda: webopen(__contact__),
        )
        menu_file.add_command(
            label='♥ ' + _('Support this project'),
            command=lambda: webopen(__support__),
        )
        menu_file.add_separator()
        menu_file.add_command(
            label=_('About'),
            command=self._show_about,
        )
        self._menu.add_cascade(
            label=_('File'),
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
            text=_('Download image galleries from the Portale Antenati'),
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
            text=_('Gallery or manifest URL'),
        ).grid(
            row=0,
            column=0,
            padx=(0, 10),
            pady=6,
            sticky=tk.W,
        )
        url_entry = ttk.Entry(
            entry_frame,
            textvariable=self._url,
        )
        url_entry.grid(
            row=0,
            column=1,
            columnspan=4,
            pady=6,
            sticky=tk.EW,
        )
        url_entry.bind('<FocusOut>', self._on_url_committed)
        url_entry.bind('<Return>', self._on_url_committed)

        self._register_panel = ttk.LabelFrame(
            entry_frame,
            text=_('Register'),
            padding=(10, 6),
            width=_REGISTER_PANEL_WIDTH,
            height=1,
        )
        self._register_panel.grid(
            row=1,
            column=4,
            rowspan=3,
            padx=(12, 0),
            pady=(8, 0),
            sticky=tk.NSEW,
        )
        self._register_panel.grid_propagate(False)
        self._register_panel.columnconfigure(0, weight=1)
        self._show_register_status(_('Enter a gallery URL to preview the register.'))

        options = ttk.LabelFrame(
            entry_frame,
            text=_('Download options'),
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
            text=_('Size (px)'),
        ).grid(
            row=0,
            column=0,
            sticky=tk.W,
            padx=(0, 8),
            pady=4,
        )
        self._size_spinbox = ttk.Spinbox(
            options,
            textvariable=self._size,
            width=10,
            from_=100,
            to=10000,
            increment=100,
        )
        self._size_spinbox.grid(
            row=0,
            column=1,
            sticky=tk.W,
            padx=(0, 10),
            pady=4,
        )
        ttk.Checkbutton(
            options,
            text=_('Maximum size'),
            variable=self._max_size,
            command=self._refresh_size_mode,
        ).grid(
            row=0,
            column=2,
            sticky=tk.W,
            pady=4,
        )

        ttk.Label(
            options,
            text=_('First page'),
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
            text=_('Zero-based index'),
        ).grid(
            row=1,
            column=2,
            sticky=tk.W,
            pady=4,
        )

        ttk.Label(
            options,
            text=_('Last page'),
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
            text=_('Exclusive; leave empty for all remaining pages'),
        ).grid(
            row=2,
            column=2,
            sticky=tk.W,
            pady=4,
        )

        ttk.Label(
            options,
            text=_('Workers'),
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
            text=_('Concurrent image downloads'),
        ).grid(
            row=3,
            column=2,
            sticky=tk.W,
            pady=4,
        )

        ttk.Label(
            options,
            text=_('Filenames'),
        ).grid(
            row=4,
            column=0,
            sticky=tk.W,
            padx=(0, 8),
            pady=4,
        )
        ttk.Checkbutton(
            options,
            text=_('Include archive/image IDs'),
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
            text=_('Existing files'),
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
            text=_('Verified resume is recommended when reusing a destination'),
        ).grid(
            row=5,
            column=2,
            sticky=tk.W,
            pady=4,
        )

        destination = ttk.LabelFrame(
            entry_frame,
            text=_('Destination'),
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
            text=_('Save in'),
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
            text=_('Change…'),
            command=self._browse_path,
        ).grid(
            row=0,
            column=2,
            padx=(10, 0),
            pady=4,
        )
        ttk.Checkbutton(
            destination,
            text=_('Create a separate folder for each register (recommended)'),
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
            text=_('Register folder'),
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
            text=_('Download'),
            command=self._on_download,
        )
        self._download_button.pack(
            side=tk.LEFT,
            padx=4,
        )
        self._cancel_button = ttk.Button(
            actions,
            text=_('Cancel'),
            command=self._on_cancel,
            state=tk.DISABLED,
        )
        self._cancel_button.pack(
            side=tk.LEFT,
            padx=4,
        )
        ttk.Button(
            actions,
            text='♥ ' + _('Support this project'),
            command=lambda: webopen(__support__),
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
            text=_('Ready'),
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
            text=_('Open folder'),
            command=self._open_output_folder,
            state=tk.DISABLED,
        )
        self._open_folder_button.pack(
            side=tk.LEFT,
            padx=(10, 0),
        )

    def _show_about(self) -> None:
        msg = f'antenati: {_("Download image galleries from the Portale Antenati")}\n'
        msg += f'{__version__}\n'
        msg += f'{__copyright__}\n\n'
        msg += f'♥ {_("Support this project")}: {__support__}'
        tkmsg.showinfo(_('About'), msg)

    def _browse_path(self) -> None:
        selected_path = tkfile.askdirectory(initialdir=self._base_path.get())
        if selected_path:
            self._base_path.set(str(Path(selected_path).resolve()))
            self._resolved_output = None
            self._open_folder_button.configure(state=tk.DISABLED)
            self._refresh_destination_mode()

    def _refresh_size_mode(self) -> None:
        self._size_spinbox.configure(state=tk.DISABLED if self._max_size.get() else tk.NORMAL)

    def _refresh_destination_mode(self) -> None:
        self._resolved_output = None
        self._open_folder_button.configure(state=tk.DISABLED)
        if self._automatic_output.get():
            self._register_folder.set(self._preview_dirname or _('Will be determined from metadata'))
        else:
            self._register_folder.set(_('(same as Save in)'))

    def _clear_register_panel(self) -> None:
        for child in self._register_panel.winfo_children():
            child.destroy()
        self._register_panel.configure(text=_('Register'))

    def _show_register_status(self, message: str, *, error: bool = False) -> None:
        self._clear_register_panel()
        ttk.Label(
            self._register_panel,
            text=message,
            foreground=_ERROR_COLOR if error else _MUTED_COLOR,
            wraplength=_REGISTER_WRAP_PX,
            justify=tk.LEFT,
        ).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky=tk.W,
        )

    def _show_register(self, preview: RegisterPreview) -> None:
        self._clear_register_panel()
        self._register_panel.configure(text=f'{_("Register")} · {_("{count} pages", count=preview.pages)}')
        for index, (label, value) in enumerate(preview.metadata):
            ttk.Label(
                self._register_panel,
                text=label,
                foreground=_MUTED_COLOR,
                font=self._caption_font,
            ).grid(
                row=2 * index,
                column=0,
                pady=(3 if index else 0, 0),
                sticky=tk.W,
            )
            is_link = value.startswith(('http://', 'https://')) and ' ' not in value
            value_label = ttk.Label(
                self._register_panel,
                text=value,
                wraplength=_REGISTER_WRAP_PX,
                justify=tk.LEFT,
                foreground=_LINK_COLOR if is_link else '',
                cursor='hand2' if is_link else '',
            )
            value_label.grid(
                row=2 * index + 1,
                column=0,
                sticky=tk.W,
            )
            if is_link:
                value_label.bind('<Button-1>', functools.partial(_open_link, value))

    def _on_url_committed(self, _event: object = None) -> None:
        url = self._url.get().strip()
        if url == self._preview_url:
            return
        self._preview_url = url
        self._preview_dirname = None
        if not url:
            self._preview.clear()
            self._preview_pending = False
            self._show_register_status(_('Enter a gallery URL to preview the register.'))
        else:
            self._show_register_status(_('Loading register metadata…'))
            self._preview.request(url)
            if not self._preview_pending:
                self._preview_pending = True
                self._root.after(_POLL_INTERVAL_MS, self._drain_preview)
        if not self._worker.is_running():
            self._refresh_destination_mode()

    def _drain_preview(self) -> None:
        try:
            while True:
                event = self._preview.events.get_nowait()
                if event.url != self._preview_url:
                    continue
                self._preview_pending = False
                if isinstance(event, RegisterPreview):
                    self._preview_dirname = event.dirname
                    self._show_register(event)
                    if not self._worker.is_running():
                        self._refresh_destination_mode()
                elif isinstance(event, PreviewFailed):
                    self._show_register_status(event.message, error=True)
        except queue.Empty:
            pass
        if self._preview_pending:
            self._root.after(_POLL_INTERVAL_MS, self._drain_preview)

    def _open_output_folder(self) -> None:
        directory = self._resolved_output
        if directory is None or not directory.is_dir():
            tkmsg.showwarning(_('Folder unavailable'), _('The destination folder does not exist yet.'))
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
            _('Existing output'),
            _('The destination already contains files.\n\nYes: resume and verify existing downloads (recommended)\nNo: choose another action\nCancel: stop'),
        )
        if resume is None:
            return None
        if resume:
            return ExistingPolicy.RESUME

        overwrite = tkmsg.askyesnocancel(
            _('Existing output'),
            _('Overwrite planned files?\n\nYes: overwrite\nNo: skip verified files and refuse ambiguous files\nCancel: stop'),
        )
        if overwrite is None:
            return None
        return ExistingPolicy.OVERWRITE if overwrite else ExistingPolicy.SKIP

    def _on_download(self) -> None:
        url = self._url.get().strip()
        if not url:
            raise RuntimeError(_('Please enter a valid URL.'))
        base_path = self._base_path.get().strip()
        automatic_output = bool(self._automatic_output.get())
        self._resolved_output = None
        self._open_folder_button.configure(state=tk.DISABLED)
        self._register_folder.set(_('Resolving…') if automatic_output else _('(same as Save in)'))

        last_raw = self._last.get().strip()
        last_val = int(last_raw) if last_raw else None
        params = DownloadParams(
            url=url,
            output_dir=None if automatic_output else base_path,
            output_base_dir=base_path,
            automatic_output=automatic_output,
            size=0 if self._max_size.get() else int(self._size.get()),
            first=int(self._first.get()),
            last=last_val,
            n_workers=int(self._n_workers.get()),
            descriptive_names=bool(self._descriptive.get()),
            existing_policy=ExistingPolicy(self._existing.get()),
        )

        self._progress = TkProgress(self._progress_bar)
        self._progress.start_indeterminate()
        self._footer_label.configure(text=_('Loading register metadata…'))
        self._terminal_received = False
        self._set_running(True)
        self._worker.start(params)
        self._root.after(
            _POLL_INTERVAL_MS,
            self._drain_events,
        )

    def _on_cancel(self) -> None:
        if self._worker.is_running():
            self._footer_label.configure(text=_('Cancelling…'))
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
                self._register_folder.set(_('(same as Save in)'))
        elif isinstance(event, ExistingOutput):
            policy = self._resolve_gui_policy(event.path, ExistingPolicy.ASK)
            if policy is None:
                self._footer_label.configure(text=_('Cancelling…'))
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
            self._footer_label.configure(text=_('Downloading {completed}/{total} pages…', completed=0, total=event.total))
        elif isinstance(event, Tick):
            if self._progress is not None:
                self._progress.update()
                self._footer_label.configure(text=_('Downloading {completed}/{total} pages…', completed=event.completed, total=self._progress.total))
        elif isinstance(event, Done):
            self._terminal_received = True
            self._set_running(False)
            report = event.report
            output = str(self._resolved_output) if self._resolved_output is not None else self._base_path.get()
            if report.successful:
                self._footer_label.configure(text=_('Download complete'))
                self._open_folder_button.configure(state=tk.NORMAL)
                tkmsg.showinfo(
                    _('Download complete'),
                    _(
                        'Downloaded {completed}, reused {skipped}. New data: {size}\n\nSaved to:\n{output}',
                        completed=report.completed,
                        skipped=report.skipped,
                        size=format_bytes(report.bytes_written),
                        output=output,
                    ),
                )
            else:
                self._footer_label.configure(text=_('Download incomplete'))
                if self._resolved_output is not None and self._resolved_output.is_dir():
                    self._open_folder_button.configure(state=tk.NORMAL)
                details = '\n'.join(f'{failure.label}: {failure.reason}' for failure in report.failed)
                tkmsg.showwarning(
                    _('Download incomplete'),
                    _(
                        'Completed {completed}/{expected}; failed {failed}.\n{details}',
                        completed=report.completed,
                        expected=report.expected,
                        failed=len(report.failed),
                        details=details,
                    ),
                )
        elif isinstance(event, Cancelled):
            self._terminal_received = True
            self._set_running(False)
            output = str(self._resolved_output) if self._resolved_output is not None else self._base_path.get()
            self._footer_label.configure(text=_('Download cancelled'))
            if self._resolved_output is not None and self._resolved_output.is_dir():
                self._open_folder_button.configure(state=tk.NORMAL)
            tkmsg.showinfo(
                _('Cancelled'),
                _('Download cancelled after {completed}/{expected} pages.', completed=event.report.completed, expected=event.report.expected),
            )
        elif isinstance(event, Failed):
            self._terminal_received = True
            self._set_running(False)
            self._footer_label.configure(text=_('Download failed'))
            if self._resolved_output is not None and self._resolved_output.is_dir():
                self._open_folder_button.configure(state=tk.NORMAL)
            tkmsg.showerror(_('Error'), event.message)

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
        tkmsg.showerror(_('Error'), f'{ex}')

    tk_root.report_callback_exception = _callback_exception
    App(tk_root, 'antenati')
    tk_root.mainloop()


if __name__ == '__main__':
    main()
