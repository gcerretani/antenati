from __future__ import annotations

from pathlib import Path

import pytest

from antenati import Downloader
from antenati.config import DownloadConfig
from antenati.output import ExistingPolicy, existing_output_requires_decision, prepare_output


def test_ask_is_shared_default() -> None:
    assert DownloadConfig(url='https://example.invalid/manifest').existing_policy is ExistingPolicy.ASK


def test_ask_detects_nonempty_output(tmp_path: Path) -> None:
    output = tmp_path / 'archive'
    output.mkdir()
    (output / 'existing.jpg').write_bytes(b'existing')
    downloader = Downloader('https://example.invalid/manifest', 0, None)

    assert existing_output_requires_decision(downloader, output)


def test_ask_does_not_prompt_for_missing_or_empty_output(tmp_path: Path) -> None:
    downloader = Downloader('https://example.invalid/manifest', 0, None)
    missing = tmp_path / 'missing'
    empty = tmp_path / 'empty'
    empty.mkdir()

    assert not existing_output_requires_decision(downloader, missing)
    assert not existing_output_requires_decision(downloader, empty)


def test_unresolved_ask_is_rejected_by_core(tmp_path: Path) -> None:
    downloader = Downloader('https://example.invalid/manifest', 0, None)

    with pytest.raises(RuntimeError, match='must be resolved by the interface'):
        prepare_output(downloader, tmp_path / 'archive', ExistingPolicy.ASK)


def test_error_policy_rejects_nonempty_explicit_output(tmp_path: Path) -> None:
    output = tmp_path / 'archive'
    output.mkdir()
    (output / 'existing.jpg').write_bytes(b'existing')
    downloader = Downloader('https://example.invalid/manifest', 0, None)

    with pytest.raises(RuntimeError, match='already exists and is not empty'):
        prepare_output(downloader, output, ExistingPolicy.ERROR)


def test_overwrite_policy_accepts_existing_output_without_deleting_it(tmp_path: Path) -> None:
    output = tmp_path / 'archive'
    output.mkdir()
    existing = output / 'existing.jpg'
    existing.write_bytes(b'existing')
    downloader = Downloader('https://example.invalid/manifest', 0, None)

    assert prepare_output(downloader, output, ExistingPolicy.OVERWRITE) == output
    assert existing.read_bytes() == b'existing'


def test_prepare_output_creates_exact_requested_directory(tmp_path: Path) -> None:
    output = tmp_path / 'chosen-name'
    downloader = Downloader('https://example.invalid/manifest', 0, None)

    assert prepare_output(downloader, output, ExistingPolicy.ERROR) == output
    assert output.is_dir()
