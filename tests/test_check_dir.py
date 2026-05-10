"""Tests for ``AntenatiDownloader.check_dir`` filesystem behaviour."""

from __future__ import annotations

from pathlib import Path

import pytest

from antenati import AntenatiDownloader


def test_check_dir_creates_target_under_parent(downloader: AntenatiDownloader, tmp_path: Path) -> None:
    downloader.check_dir(parentdir=str(tmp_path), interactive=False)
    assert downloader.dirname.is_dir()
    assert downloader.dirname.parent == tmp_path


def test_check_dir_raises_when_target_exists_and_non_interactive(downloader: AntenatiDownloader, tmp_path: Path) -> None:
    target = tmp_path / str(downloader.dirname)
    target.mkdir()
    with pytest.raises(RuntimeError, match='already exists'):
        downloader.check_dir(parentdir=str(tmp_path), interactive=False)


def test_check_dir_without_parent_uses_cwd(downloader: AntenatiDownloader, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    downloader.check_dir(interactive=False)
    assert (tmp_path / downloader.dirname).is_dir()
