"""Tk-free unit tests for the GUI worker state machine."""

from __future__ import annotations

import queue
from pathlib import Path
from typing import Any

import pytest

from antenati.downloader import DownloadReport, ProgressBar
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


class _FakeDownloader:
    def __init__(
        self,
        n_canvases: int = 3,
        total_bytes: int = 42,
        raise_in_run: Exception | None = None,
        block_for_cancel: bool = False,
        dirname: Path | None = None,
    ) -> None:
        self.dirname = dirname or Path('ignored')
        self._n_canvases = n_canvases
        self._total_bytes = total_bytes
        self._raise = raise_in_run
        self._block_for_cancel = block_for_cancel
        self.loaded = False

    @property
    def gallery_length(self) -> int:
        return self._n_canvases

    def load(self):
        self.loaded = True
        return self

    def run(self, n_workers: int, size: int, progress: ProgressBar, cancel=None, *, resume: bool = False) -> DownloadReport:
        del n_workers, size, resume
        if self._raise is not None:
            raise self._raise
        progress.set_total(self._n_canvases)
        if self._block_for_cancel and cancel is not None:
            cancel.wait(timeout=2.0)
            return DownloadReport(self._n_canvases, 0, 0, 0, (), True, 0)
        for _ in range(self._n_canvases):
            progress.update()
        return DownloadReport(self._n_canvases, self._n_canvases, self._n_canvases, 0, (), False, self._total_bytes)


def _drain_events(worker: DownloadWorker, timeout: float = 2.0) -> list[Any]:
    worker.join(timeout=timeout)
    events: list[Any] = []
    try:
        while True:
            events.append(worker.events.get_nowait())
    except queue.Empty:
        return events


def _params(tmp_path: Path, *, output_dir: str | None = None, policy: ExistingPolicy = ExistingPolicy.OVERWRITE) -> DownloadParams:
    return DownloadParams(
        url='https://example.org/gallery',
        output_dir=output_dir if output_dir is not None else str(tmp_path / 'out'),
        size=0,
        first=0,
        last=None,
        existing_policy=policy,
    )


def test_happy_path_emits_destination_phases_progress_ticks_and_done(tmp_path: Path) -> None:
    output = tmp_path / 'out'
    fake = _FakeDownloader(n_canvases=3, total_bytes=12345)
    worker = DownloadWorker(factory=lambda url, first, last, descriptive_names=False: fake)
    worker.start(_params(tmp_path))
    events = _drain_events(worker)

    destinations = [event for event in events if isinstance(event, Destination)]
    assert [event.path for event in destinations] == [str(output)]

    phases = [event for event in events if isinstance(event, Phase)]
    assert [phase.message for phase in phases] == ['Loading register metadata…', 'Preparing output…', 'Planning download…']

    progress_events = [event for event in events if isinstance(event, Progress)]
    assert len(progress_events) == 1
    assert progress_events[0].total == 3

    ticks = [event for event in events if isinstance(event, Tick)]
    assert [tick.completed for tick in ticks] == [1, 2, 3]

    assert isinstance(events[-1], Done)
    assert events[-1].report.bytes_written == 12345
    assert fake.loaded


def test_empty_output_uses_generated_register_directory(tmp_path: Path) -> None:
    generated = tmp_path / 'generated-register'
    fake = _FakeDownloader(dirname=generated)
    worker = DownloadWorker(factory=lambda url, first, last, descriptive_names=False: fake)
    params = _params(tmp_path)
    params.output_dir = None

    worker.start(params)
    events = _drain_events(worker)

    destination = next(event for event in events if isinstance(event, Destination))
    assert destination.path == str(generated)
    assert generated.is_dir()
    assert isinstance(events[-1], Done)


def test_ask_policy_on_generated_existing_output_waits_for_gui_choice(tmp_path: Path) -> None:
    generated = tmp_path / 'generated-register'
    generated.mkdir()
    (generated / 'existing.txt').write_text('existing', encoding='utf-8')
    fake = _FakeDownloader(dirname=generated)
    worker = DownloadWorker(factory=lambda url, first, last, descriptive_names=False: fake)
    params = _params(tmp_path, policy=ExistingPolicy.ASK)
    params.output_dir = None

    worker.start(params)
    seen: list[Any] = []
    while True:
        event = worker.events.get(timeout=2.0)
        seen.append(event)
        if isinstance(event, ExistingOutput):
            break

    assert event.path == str(generated)
    assert worker.is_running()

    worker.resolve_existing_policy(ExistingPolicy.RESUME)
    remaining = _drain_events(worker)

    assert any(isinstance(item, Destination) for item in seen)
    assert isinstance(remaining[-1], Done)


def test_constructor_failure_emits_phase_then_failed_event(tmp_path: Path) -> None:
    def boom(url: str, first: int, last: int | None, descriptive_names: bool = False):
        del url, first, last, descriptive_names
        raise RuntimeError('manifest blew up')

    worker = DownloadWorker(factory=boom)
    worker.start(_params(tmp_path))
    events = _drain_events(worker)
    assert isinstance(events[0], Phase)
    assert isinstance(events[-1], Failed)
    assert 'manifest blew up' in events[-1].message


def test_run_failure_emits_failed_event(tmp_path: Path) -> None:
    fake = _FakeDownloader(raise_in_run=RuntimeError('disk full'))
    worker = DownloadWorker(factory=lambda url, first, last, descriptive_names=False: fake)
    worker.start(_params(tmp_path))
    failures = [event for event in _drain_events(worker) if isinstance(event, Failed)]
    assert len(failures) == 1
    assert 'disk full' in failures[0].message


def test_cancel_before_completion_emits_cancelled_event(tmp_path: Path) -> None:
    fake = _FakeDownloader(n_canvases=10, block_for_cancel=True)
    worker = DownloadWorker(factory=lambda url, first, last, descriptive_names=False: fake)
    worker.start(_params(tmp_path))
    worker.cancel()
    events = _drain_events(worker)
    assert any(isinstance(event, Cancelled) for event in events)
    assert not any(isinstance(event, Done) for event in events)


def test_starting_twice_while_running_raises(tmp_path: Path) -> None:
    fake = _FakeDownloader(block_for_cancel=True)
    worker = DownloadWorker(factory=lambda url, first, last, descriptive_names=False: fake)
    worker.start(_params(tmp_path))
    with pytest.raises(RuntimeError, match='already in progress'):
        worker.start(_params(tmp_path))
    worker.cancel()
    _drain_events(worker)


def test_is_running_flips_around_thread_lifetime(tmp_path: Path) -> None:
    fake = _FakeDownloader(n_canvases=1)
    worker = DownloadWorker(factory=lambda url, first, last, descriptive_names=False: fake)
    assert worker.is_running() is False
    worker.start(_params(tmp_path))
    worker.join(timeout=2.0)
    assert worker.is_running() is False
