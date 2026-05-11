"""Unit tests for :mod:`antenati.gui.worker`.

These tests stay completely Tk-free: they exercise the worker thread by
injecting fake :class:`Downloader` objects and asserting the sequence of
events that lands on the worker's queue. The real GUI just polls that
queue, so getting these events right is enough to guarantee the UI
behaves correctly.
"""

from __future__ import annotations

import queue
from pathlib import Path
from typing import Any

import pytest

from antenati.downloader import ProgressBar
from antenati.gui.worker import (
    Cancelled,
    Done,
    DownloadParams,
    DownloadWorker,
    Failed,
    Progress,
    Tick,
)


class _FakeDownloader:
    """Minimal Downloader stand-in: pumps a fixed number of ticks and ends."""

    def __init__(
        self,
        n_canvases: int = 3,
        total_bytes: int = 42,
        raise_in_run: Exception | None = None,
        cancel_after: int | None = None,
    ) -> None:
        self.gallery_length = n_canvases
        self.dirname = Path('ignored')
        self._n_canvases = n_canvases
        self._total_bytes = total_bytes
        self._raise = raise_in_run
        self._cancel_after = cancel_after
        self.check_dir_called_with: tuple[str, bool] | None = None

    def check_dir(self, parent_dir: str, interactive: bool) -> None:
        self.check_dir_called_with = (parent_dir, interactive)

    def run(self, n_workers: int, size: int, progress: ProgressBar, cancel=None) -> int:
        if self._raise is not None:
            raise self._raise
        progress.set_total(self._n_canvases)
        if self._cancel_after is not None and cancel is not None:
            for _ in range(self._cancel_after):
                progress.update()
            # Block until the test calls worker.cancel(); mirrors the
            # real Downloader's "stop at next canvas boundary" behaviour.
            cancel.wait(timeout=2.0)
            return self._total_bytes // 2
        for _ in range(self._n_canvases):
            progress.update()
        return self._total_bytes


def _drain_events(worker: DownloadWorker, timeout: float = 2.0) -> list[Any]:
    """Collect all events the worker pushes until the thread finishes."""
    worker.join(timeout=timeout)
    events: list[Any] = []
    try:
        while True:
            events.append(worker.events.get_nowait())
    except queue.Empty:
        pass
    return events


def _params() -> DownloadParams:
    return DownloadParams(
        url='https://example.org/gallery',
        parent_dir='/tmp/x',
        size=0,
        first=0,
        last=None,
    )


def test_happy_path_emits_progress_ticks_and_done() -> None:
    fake = _FakeDownloader(n_canvases=3, total_bytes=12345)
    worker = DownloadWorker(factory=lambda url, first, last: fake)
    worker.start(_params())
    events = _drain_events(worker)

    assert isinstance(events[0], Progress)
    assert events[0].total == 3
    assert sum(1 for e in events if isinstance(e, Tick)) == 3
    assert isinstance(events[-1], Done)
    assert events[-1].total_bytes == 12345


def test_check_dir_is_called_with_parent_and_non_interactive() -> None:
    fake = _FakeDownloader(n_canvases=1)
    worker = DownloadWorker(factory=lambda url, first, last: fake)
    worker.start(_params())
    _drain_events(worker)
    assert fake.check_dir_called_with == ('/tmp/x', False)


def test_constructor_failure_emits_failed_event() -> None:
    def boom(url: str, first: int, last: int | None):
        raise RuntimeError('manifest blew up')

    worker = DownloadWorker(factory=boom)
    worker.start(_params())
    events = _drain_events(worker)
    assert len(events) == 1
    assert isinstance(events[0], Failed)
    assert 'manifest blew up' in events[0].message


def test_run_failure_emits_failed_event() -> None:
    fake = _FakeDownloader(raise_in_run=RuntimeError('disk full'))
    worker = DownloadWorker(factory=lambda url, first, last: fake)
    worker.start(_params())
    events = _drain_events(worker)
    failures = [e for e in events if isinstance(e, Failed)]
    assert len(failures) == 1
    assert 'disk full' in failures[0].message


def test_cancel_before_completion_emits_cancelled_event() -> None:
    # Have the fake check the cancel event and return early.
    fake = _FakeDownloader(n_canvases=10, cancel_after=2)
    worker = DownloadWorker(factory=lambda url, first, last: fake)
    worker.start(_params())
    worker.cancel()
    events = _drain_events(worker)
    assert any(isinstance(e, Cancelled) for e in events)
    assert not any(isinstance(e, Done) for e in events)


def test_starting_twice_while_running_raises() -> None:
    # cancel_after=0 + factory returns a fake that blocks on cancel.wait()
    # gives us a worker that's guaranteed to be alive when start() is
    # called a second time.
    fake = _FakeDownloader(n_canvases=1, cancel_after=0)
    worker = DownloadWorker(factory=lambda url, first, last: fake)
    worker.start(_params())
    with pytest.raises(RuntimeError, match='already in progress'):
        worker.start(_params())
    worker.cancel()
    _drain_events(worker)


def test_is_running_flips_around_the_thread_lifetime() -> None:
    fake = _FakeDownloader(n_canvases=1)
    worker = DownloadWorker(factory=lambda url, first, last: fake)
    assert worker.is_running() is False
    worker.start(_params())
    worker.join(timeout=2.0)
    assert worker.is_running() is False
