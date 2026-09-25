from __future__ import annotations

from pathlib import Path

import pytest

from antenati import filesystem


def _windows_error(winerror: int) -> PermissionError:
    exc = PermissionError('transient Windows file lock')
    exc.winerror = winerror
    return exc


def test_atomic_replace_retries_transient_windows_access_denied(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = tmp_path / 'source.tmp'
    target = tmp_path / 'target.jpg'
    source.write_bytes(b'new')
    target.write_bytes(b'old')

    real_replace = filesystem.os.replace
    calls = [0]

    def flaky_replace(src, dst) -> None:
        calls[0] += 1
        if calls[0] < 3:
            raise _windows_error(5)
        real_replace(src, dst)

    monkeypatch.setattr(filesystem, '_IS_WINDOWS', True)
    monkeypatch.setattr(filesystem.os, 'replace', flaky_replace)
    monkeypatch.setattr(filesystem.time, 'sleep', lambda _seconds: None)

    filesystem.atomic_replace(source, target)

    assert calls[0] == 3
    assert target.read_bytes() == b'new'
    assert not source.exists()


def test_atomic_replace_does_not_retry_unrelated_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = tmp_path / 'source.tmp'
    target = tmp_path / 'target.jpg'
    source.write_bytes(b'new')
    calls = [0]

    def failing_replace(_src, _dst) -> None:
        calls[0] += 1
        raise FileNotFoundError('not transient')

    monkeypatch.setattr(filesystem, '_IS_WINDOWS', True)
    monkeypatch.setattr(filesystem.os, 'replace', failing_replace)
    monkeypatch.setattr(filesystem.time, 'sleep', lambda _seconds: None)

    with pytest.raises(FileNotFoundError):
        filesystem.atomic_replace(source, target)

    assert calls[0] == 1
