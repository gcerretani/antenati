# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Background download worker for the Tk GUI."""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from typing import Protocol

from antenati.config import DownloadConfig
from antenati.downloader import Downloader, DownloadReport, ProgressBar
from antenati.output import ExistingPolicy, existing_output_requires_decision, output_directory, prepare_output, run_with_policy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Phase:
    message: str


@dataclass(frozen=True)
class Destination:
    path: str


@dataclass(frozen=True)
class ExistingOutput:
    path: str


@dataclass(frozen=True)
class Progress:
    total: int


@dataclass(frozen=True)
class Tick:
    completed: int


@dataclass(frozen=True)
class Done:
    report: DownloadReport


@dataclass(frozen=True)
class Cancelled:
    report: DownloadReport


@dataclass(frozen=True)
class Failed:
    message: str


WorkerEvent = Phase | Destination | ExistingOutput | Progress | Tick | Done | Cancelled | Failed


@dataclass
class DownloadParams(DownloadConfig):
    """Backward-compatible GUI name for the shared download configuration."""


class DownloaderFactory(Protocol):
    def __call__(self, url: str, first: int, last: int | None, descriptive_names: bool = False) -> Downloader: ...


def _default_factory(url: str, first: int, last: int | None, descriptive_names: bool = False) -> Downloader:
    return Downloader(url, first, last, descriptive_names=descriptive_names)


class DownloadWorker:
    def __init__(self, factory: DownloaderFactory = _default_factory) -> None:
        self._factory = factory
        self.events: queue.Queue[WorkerEvent] = queue.Queue()
        self._policy_responses: queue.Queue[ExistingPolicy] = queue.Queue()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, params: DownloadParams) -> None:
        params.validate()
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError('A download is already in progress')
        self._cancel.clear()
        self._clear_policy_responses()
        self._thread = threading.Thread(target=self._run, args=(params,), name='antenati-download', daemon=True)
        self._thread.start()

    def resolve_existing_policy(self, policy: ExistingPolicy) -> None:
        if policy is ExistingPolicy.ASK:
            raise ValueError('ExistingPolicy.ASK cannot resolve an existing-output prompt')
        self._policy_responses.put(policy)

    def cancel(self) -> None:
        self._cancel.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def _clear_policy_responses(self) -> None:
        try:
            while True:
                self._policy_responses.get_nowait()
        except queue.Empty:
            pass

    def _cancelled_report(self, downloader: Downloader) -> DownloadReport:
        return DownloadReport(
            expected=downloader.gallery_length,
            attempted=0,
            completed=0,
            skipped=0,
            failed=(),
            cancelled=True,
            bytes_written=0,
        )

    def _resolve_policy(self, downloader: Downloader, params: DownloadParams) -> ExistingPolicy | None:
        if params.existing_policy is not ExistingPolicy.ASK:
            return params.existing_policy
        if not existing_output_requires_decision(downloader, params.output_dir):
            return ExistingPolicy.ERROR

        directory = output_directory(downloader, params.output_dir)
        self.events.put(ExistingOutput(path=str(directory)))
        while not self._cancel.is_set():
            try:
                return self._policy_responses.get(timeout=0.1)
            except queue.Empty:
                continue
        return None

    def _run(self, params: DownloadParams) -> None:
        try:
            params.validate()
            self.events.put(Phase('Loading register metadata…'))
            downloader = self._factory(params.url, params.first, params.last, params.descriptive_names)
            downloader.load()

            directory = output_directory(downloader, params.output_dir)
            self.events.put(Destination(path=str(directory)))

            policy = self._resolve_policy(downloader, params)
            if policy is None:
                self.events.put(Cancelled(report=self._cancelled_report(downloader)))
                return

            self.events.put(Phase('Preparing output…'))
            prepare_output(downloader, params.output_dir, policy)

            completed = 0

            def tick() -> None:
                nonlocal completed
                completed += 1
                self.events.put(Tick(completed=completed))

            progress = ProgressBar(
                set_total=lambda total: self.events.put(Progress(total=total)),
                update=tick,
            )
            self.events.put(Phase('Planning download…'))
            report = run_with_policy(
                downloader,
                n_workers=params.n_workers,
                size=params.size,
                progress=progress,
                policy=policy,
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
