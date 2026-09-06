from __future__ import annotations

from pathlib import Path

import pytest

from antenati import Downloader
from antenati.output import ExistingPolicy, prepare_output


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
