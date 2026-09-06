# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Background download worker for the Tk GUI."""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from typing import Protocol

from antenati.downloader import DEFAULT_N_THREADS, DownloadReport, Downloader, ProgressBar

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Progress:
    """Total work-units have been announced by the downloader."""

    total: int


@dataclass(frozen=True)
class Tick:
    """A single image finished (success or failure)."""


@dataclass(frozen=True)
class Done:
    """Execution finished; ``report`` contains the complete outcome."""

    report: DownloadReport


@dataclass(frozen=True)
class Cancelled:
    """The user clicked Cancel and the worker honoured the request."""

    report: DownloadReport


@dataclass(frozen=True)
class Failed:
    """The worker hit an unrecoverable error before producing a report."""

    message: str


WorkerEvent = Progress | Tick | Done | Cancelled | Failed


@dataclass
class DownloadParams:
    """Inputs the worker needs to start a download."""

    url: str
    parent_dir: str
    size: int
    first: int
    last: int | None
    n_workers: int = DEFAULT_N_THREADS


class DownloaderFactory(Protocol):
    def __call__(self, url: str, first: int, last: int | None) -> Downloader: ...


def _default_factory(url: str, first: int, last: int | None) -> Downloader:
    return Downloader(url, first, last)


class DownloadWorker:
    """Run a download on a background thread, surface events on a Queue."""

    def __init__(self, factory: DownloaderFactory = _default_factory) -> None:
        self._factory = factory
        self.events: queue.Queue[WorkerEvent] = queue.Queue()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, params: DownloadParams) -> None:
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError('A download is already in progress')
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, args=(params,), name='antenati-download', daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self, params: DownloadParams) -> None:
        try:
            downloader = self._factory(params.url, params.first, params.last)
            downloader.load()
            downloader.check_dir(params.parent_dir, interactive=False)
            progress = ProgressBar(
                set_total=lambda total: self.events.put(Progress(total=total)),
                update=lambda: self.events.put(Tick()),
            )
            report = downloader.run(params.n_workers, params.size, progress, cancel=self._cancel)
        except Exception as ex:
            logger.exception('Download worker failed')
            self.events.put(Failed(message=str(ex)))
            return

        if report.cancelled:
            self.events.put(Cancelled(report=report))
        else:
            self.events.put(Done(report=report))
