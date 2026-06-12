# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Background download worker for the Tk GUI.

The worker runs the entire ``Downloader`` lifecycle (construction, manifest
fetch, image downloads) on a dedicated ``threading.Thread`` and reports
back to the main thread by pushing events onto a :class:`queue.Queue`.
The Tk event loop then polls that queue with ``root.after`` and updates
the UI without blocking.

Compared to the legacy ``ThreadPoolExecutor(max_workers=1) +
wait_variable`` pattern this gives us three things:

1. The main loop is never blocked, so the window keeps repainting
   (and the Cancel button can be clicked) while the download runs.
2. Exceptions surface cleanly via a ``Failed`` event with the full
   message; they no longer get swallowed by the ``with`` cleanup.
3. The whole thing is dependency-free for tests — :func:`run_worker`
   only needs a ``DownloaderFactory`` callable and a ``ProgressBar`` to
   pump events into a queue, so unit tests can exercise the state
   machine without any Tk import.
"""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from typing import Protocol

from antenati.downloader import DEFAULT_N_THREADS, Downloader, ProgressBar

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
    """All images processed; ``total_bytes`` is the cumulative download size."""

    total_bytes: int


@dataclass(frozen=True)
class Cancelled:
    """The user clicked Cancel and the worker honoured the request."""


@dataclass(frozen=True)
class Failed:
    """The worker hit an unrecoverable error before completing."""

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
    """Callable that builds a Downloader. Tests inject a fake here."""

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
        """Spawn the download thread. Returns immediately."""
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError('A download is already in progress')
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, args=(params,), name='antenati-download', daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        """Ask the running download to stop at the next canvas boundary."""
        self._cancel.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def join(self, timeout: float | None = None) -> None:
        """Wait for the worker to finish (mainly useful in tests)."""
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self, params: DownloadParams) -> None:
        try:
            downloader = self._factory(params.url, params.first, params.last)
            downloader.check_dir(params.parent_dir, interactive=False)

            progress = ProgressBar(
                set_total=lambda total: self.events.put(Progress(total=total)),
                update=lambda: self.events.put(Tick()),
            )
            total_bytes = downloader.run(params.n_workers, params.size, progress, cancel=self._cancel)
        except Exception as ex:
            logger.exception('Download worker failed')
            self.events.put(Failed(message=str(ex)))
            return

        if self._cancel.is_set():
            self.events.put(Cancelled())
        else:
            self.events.put(Done(total_bytes=total_bytes))
