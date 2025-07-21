#!/usr/bin/env python3
"""
antenati_gui.py: a GUI tool to download data from the Portale Antenati
"""

__author__ = 'Giovanni Cerretani'
__copyright__ = 'Copyright (c) 2022, Giovanni Cerretani'
__license__ = 'MIT License'
__contact__ = 'https://gcerretani.github.io/antenati/'

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
import tkinter as tk
import tkinter.filedialog as tkfile
import tkinter.messagebox as tkmsg
import tkinter.ttk as ttk
from webbrowser import open as webopen

from humanize import naturalsize

import antenati


@dataclass
class _ProgressBarSetter:
    progress_bar: ttk.Progressbar
    total: int = field(default=0)
    n: int = field(default=0)

    def set_total(self, total: int):
        """Set max value"""
        self.total = total

    def __set(self, value: float) -> None:
        """Set progress bar value"""
        self.progress_bar['value'] = value

    def reset(self) -> None:
        """Reset"""
        self.total = 0
        self.n = 0
        self.__set(0)

    def update(self) -> None:
        """Set progress bar value in main Tk thread"""
        self.n += 1
        percent_completed = 100 * self.n / self.total
        self.progress_bar.master.after(0, self.__set, percent_completed)


@dataclass
class _CompletedFlag:
    _variable: tk.BooleanVar

    @contextmanager
    def set_at_exit(self):
        """To be used in a with-statement"""
        try:
            yield
        finally:
            self._variable.set(True)


class _Window:
    def __init__(self, root: tk.Tk, title: str):
        self.__root = root
        self.__root.minsize(400, 100)
        self.__root.title(title.strip())

        # Create menu
        self.__menu = tk.Menu(self.__root)
        self.__root.configure(menu=self.__menu)

        # Populate entries
        self.__create_menu()
        self.__create_entries()
        self.__create_footer()

    def __create_menu(self):
        menu_file = tk.Menu(self.__menu, tearoff=0)
        menu_file.add_command(label='Portale Antenati Website', command=lambda: webopen('https://antenati.cultura.gov.it/'))
        menu_file.add_command(label='Project Website', command=lambda: webopen(__contact__))
        menu_file.add_separator()
        menu_file.add_command(label='About', command=self.__about)
        self.__menu.add_cascade(label='File', menu=menu_file)

    def __create_entries(self):
        entry_frame = ttk.Frame(self.__root)
        entry_frame.pack(side=tk.TOP, fill=tk.X)
        url_label = tk.Label(entry_frame, text='Archive URL')
        url_label.grid(row=0, column=0, padx=10, pady=5, sticky=tk.W)
        self.__url_textvariable = tk.StringVar()
        url_entry = ttk.Entry(entry_frame, textvariable=self.__url_textvariable, width=100)
        url_entry.grid(row=0, column=1, padx=10, pady=5, columnspan=2, sticky=tk.EW)
        self.__path_textvariable = tk.StringVar()
        path_label = tk.Label(entry_frame, text='Destination folder')
        path_label.grid(row=1, column=0, padx=10, pady=5, sticky=tk.EW)
        path_entry = ttk.Entry(entry_frame, textvariable=self.__path_textvariable, width=100)
        path_entry.grid(row=1, column=1, padx=10, pady=5, sticky=tk.EW)
        browse_button = ttk.Button(entry_frame, text='Browse', command=self.__browse_path)
        browse_button.grid(row=1, column=2, padx=10, pady=5, sticky=tk.EW)
        self.__download_button = ttk.Button(entry_frame, text='Download', command=self.__download)
        self.__download_button.grid(row=2, column=1, padx=5, pady=5)
        download_button = ttk.Button(entry_frame, text='Support this project', command=lambda: webopen('https://ko-fi.com/gcerretani'))
        download_button.grid(row=3, column=1, padx=5, pady=5)

    def __create_footer(self):
        footer_frame = ttk.Frame(self.__root)
        footer_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.__footer_label = ttk.Label(footer_frame, anchor=tk.W)
        self.__footer_label.grid(row=0, column=0, padx=2, pady=2, sticky=tk.EW)
        self.__footer_led = ttk.Label(footer_frame, anchor=tk.CENTER, width=18)
        self.__footer_led.grid(row=0, column=1, padx=2, pady=2, sticky=tk.EW)
        footer_frame.columnconfigure(0, weight=1)
        self.__progress_bar = ttk.Progressbar(self.__root, mode='determinate', orient=tk.HORIZONTAL)
        self.__progress_bar.pack(side=tk.BOTTOM, fill=tk.BOTH, padx=2, pady=2)

    def __about(self) -> None:
        """Show about popup"""
        msg = f'{__doc__.strip()}'
        msg += f'\n{antenati.__version__}'
        msg += f'\n{__copyright__}'
        tkmsg.showinfo('About', msg)

    def __browse_path(self):
        selected_path = tkfile.askdirectory()
        if selected_path:
            self.__path_textvariable.set(selected_path)

    @contextmanager
    def __wait_flag(self):
        variable = tk.BooleanVar(value=False)
        try:
            yield _CompletedFlag(variable)
        finally:
            self.__root.wait_variable(variable)

    def __download(self):
        url = self.__url_textvariable.get()
        if len(url) == 0:
            raise RuntimeError('Please enter a valid URL.')
        path_value = self.__path_textvariable.get()
        if len(path_value) == 0:
            raise RuntimeError('Please enter a valid destination folder.')
        downloader = antenati.AntenatiDownloader(url, 0, None)
        downloader.check_dir(path_value, False)
        with ThreadPoolExecutor(max_workers=1) as exc, self.__progress_bar_setter() as pb, self.__in_progress(), self.__wait_flag() as flag:
            def cmd():
                with flag.set_at_exit():
                    progressbar = antenati.ProgressBar(pb.set_total, pb.update)
                    return downloader.run(antenati.DEFAULT_N_THREADS, antenati.DEFAULT_N_CONNECTIONS, antenati.DEFAULT_WIDTH, progressbar)
            future = exc.submit(cmd)
        gallery_size = future.result()
        tkmsg.showinfo('Success', f'Operation completed successfully. Total size: {naturalsize(gallery_size, True)}')

    @contextmanager
    def __in_progress(self):
        """Context manager to disable buttons"""
        self.__download_button.configure(state=tk.DISABLED)
        self.__footer_label.configure(text='Operation in progress...')
        try:
            yield
        finally:
            self.__footer_label.configure(text='')
            self.__download_button.configure(state=tk.NORMAL)

    @contextmanager
    def __progress_bar_setter(self):
        """Context manager for progress bar"""
        setter = _ProgressBarSetter(self.__progress_bar)
        try:
            yield setter
        finally:
            setter.reset()  # Reset value


if __name__ == '__main__':
    tk_root = tk.Tk()
    def __callback_exception(_type, ex: BaseException, _traceback):
        tkmsg.showerror('Error', f'{ex}')
    tk_root.report_callback_exception = __callback_exception
    app = _Window(tk_root, __doc__)
    tk_root.mainloop()
