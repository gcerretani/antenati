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
from antenati.output import ExistingPolicy, prepare_output, run_with_policy
from antenati.validation import DownloadOptions

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Progress:
    total: int


@dataclass(frozen=True)
class Tick:
    pass


@dataclass(frozen=True)
class Done:
    report: DownloadReport


@dataclass(frozen=True)
class Cancelled:
    report: DownloadReport


@dataclass(frozen=True)
class Failed:
    message: str


WorkerEvent = Progress | Tick | Done | Cancelled | Failed


@dataclass
class DownloadParams:
    url: str
    output_dir: str
    size: int
    first: int
    last: int | None
    n_workers: int = DEFAULT_N_THREADS
    existing_policy: ExistingPolicy = ExistingPolicy.ERROR
    descriptive_names: bool = False

    def options(self) -> DownloadOptions:
        return DownloadOptions(first=self.first, last=self.last, size=self.size, n_workers=self.n_workers)

    def validate(self) -> DownloadParams:
        self.options().validate()
        if not self.url.strip():
            from antenati.errors import ValidationError

            raise ValidationError('url must not be empty')
        if not self.output_dir.strip():
            from antenati.errors import ValidationError

            raise ValidationError('output directory must not be empty')
        return self


class DownloaderFactory(Protocol):
    def __call__(self, url: str, first: int, last: int | None, descriptive_names: bool = False) -> Downloader: ...


def _default_factory(url: str, first: int, last: int | None, descriptive_names: bool = False) -> Downloader:
    return Downloader(url, first, last, descriptive_names=descriptive_names)


class DownloadWorker:
    def __init__(self, factory: DownloaderFactory = _default_factory) -> None:
        self._factory = factory
        self.events: queue.Queue[WorkerEvent] = queue.Queue()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, params: DownloadParams) -> None:
        params.validate()
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
            params.validate()
            downloader = self._factory(params.url, params.first, params.last, params.descriptive_names)
            downloader.load()
            prepare_output(downloader, params.output_dir, params.existing_policy)
            progress = ProgressBar(
                set_total=lambda total: self.events.put(Progress(total=total)),
                update=lambda: self.events.put(Tick()),
            )
            report = run_with_policy(
                downloader,
                n_workers=params.n_workers,
                size=params.size,
                progress=progress,
                policy=params.existing_policy,
                cancel=self._cancel,
            )
        except Exception as ex:
            logger.exception('Download worker failed')
            self.events.put(Failed(message=str(ex)))
            return

        if report.cancelled:
            self.events.put(Cancelled(report=report))
        else:
            self.events.put(Done(report=report))
