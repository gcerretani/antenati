"""Offline functional tests built on the shared mocked HTTP fixtures.

These tests keep CLI parsing, downloader orchestration, filesystem writes,
provenance and resume behavior real while mocking only external HTTP traffic.
Live compatibility with the Portale Antenati remains covered separately by the
opt-in integration canaries.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import responses

from antenati import Downloader, ProgressBar
from antenati import cli as antenati_cli
from antenati.output import ExistingPolicy, prepare_output, run_with_policy
from tests.conftest import MANIFEST_URL, TINY_JPEG

_LABELS = ('0001', '0002', '0003')
_IMAGE_PREFIX = 'https://iiif.example.org/iiif/img'


def _progress() -> ProgressBar:
    return ProgressBar(set_total=lambda _total: None, update=lambda: None)


def _image_url(label: str, size: int = 0) -> str:
    size_part = f'!{size},{size}' if size > 0 else 'pct:100'
    return f'{_IMAGE_PREFIX}{label[-1]}/full/{size_part}/0/default.jpg'


def _register_jpegs(mocked_http, *, size: int = 0, corrupt_label: str | None = None) -> None:
    for label in _LABELS:
        payload = b'not-a-jpeg' if label == corrupt_label else TINY_JPEG
        mocked_http.add(responses.GET, _image_url(label, size), body=payload, status=200, content_type='image/jpeg')


def _image_request_count(mocked_http) -> int:
    return sum(1 for call in mocked_http.calls if str(call.request.url).startswith(_IMAGE_PREFIX))


def _run(source_url: str, output: Path, *, size: int = 0, policy: ExistingPolicy = ExistingPolicy.OVERWRITE):
    downloader = Downloader(source_url, first=0, last=None)
    downloader.load()
    prepare_output(downloader, output, policy)
    return run_with_policy(downloader, n_workers=3, size=size, progress=_progress(), policy=policy)


def _image_names(output: Path) -> list[str]:
    return sorted(path.name for path in output.glob('*.jpg'))


def _invoke_cli(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    monkeypatch.setattr(sys, 'argv', ['antenati', *args])
    try:
        antenati_cli.main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    else:
        code = 0
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_resume_redownloads_only_missing_file(mocked_http, tmp_path: Path) -> None:
    _register_jpegs(mocked_http)
    output = tmp_path / 'archive'
    _run(MANIFEST_URL, output)
    (output / '0002.jpg').unlink()
    image_calls_before = _image_request_count(mocked_http)

    report = _run(MANIFEST_URL, output, policy=ExistingPolicy.RESUME)

    assert report.successful
    assert report.completed == 1
    assert report.skipped == 2
    assert _image_request_count(mocked_http) == image_calls_before + 1
    assert (output / '0002.jpg').read_bytes() == TINY_JPEG


def test_corrupt_remote_image_is_not_committed(mocked_http, tmp_path: Path) -> None:
    _register_jpegs(mocked_http, corrupt_label='0002')
    output = tmp_path / 'archive'

    report = _run(MANIFEST_URL, output)

    assert not report.successful
    assert report.completed == 2
    assert len(report.failed) == 1
    assert not (output / '0002.jpg').exists()
    assert not list(output.glob('*.tmp'))


def test_cli_dry_run_downloads_no_images(
    mocked_http,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _register_jpegs(mocked_http)
    output = tmp_path / 'archive'
    image_calls_before = _image_request_count(mocked_http)

    code, stdout, stderr = _invoke_cli(monkeypatch, capsys, MANIFEST_URL, '--output', str(output), '--dry-run')

    assert code == 0, stderr
    assert '0001.jpg' in stdout
    assert '0003.jpg' in stdout
    assert _image_request_count(mocked_http) == image_calls_before
    assert not output.exists()


def test_cli_default_ask_can_resume_existing_download(
    mocked_http,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _register_jpegs(mocked_http)
    output = tmp_path / 'archive'
    first_code, _, first_stderr = _invoke_cli(monkeypatch, capsys, MANIFEST_URL, '--output', str(output), '--existing', 'overwrite')
    assert first_code == 0, first_stderr
    image_calls_before = _image_request_count(mocked_http)
    monkeypatch.setattr(antenati_cli.click, 'prompt', lambda *_args, **_kwargs: 'resume')

    resumed_code, resumed_stdout, resumed_stderr = _invoke_cli(monkeypatch, capsys, MANIFEST_URL, '--output', str(output))

    assert resumed_code == 0, resumed_stderr
    assert 'Choose how to handle existing files' in resumed_stdout
    assert 'skipped: 3' in resumed_stdout
    assert _image_request_count(mocked_http) == image_calls_before


def test_cli_explicit_error_policy_rejects_existing_output_without_image_requests(
    mocked_http,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _register_jpegs(mocked_http)
    output = tmp_path / 'archive'
    first_code, _, first_stderr = _invoke_cli(monkeypatch, capsys, MANIFEST_URL, '--output', str(output), '--existing', 'overwrite')
    assert first_code == 0, first_stderr
    image_calls_before = _image_request_count(mocked_http)
    monkeypatch.setattr(sys, 'argv', ['antenati', MANIFEST_URL, '--output', str(output), '--existing', 'error'])

    with pytest.raises(RuntimeError, match='already exists and is not empty'):
        antenati_cli.main()

    capsys.readouterr()
    assert _image_request_count(mocked_http) == image_calls_before
