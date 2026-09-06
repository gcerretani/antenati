"""End-to-end correctness tests for ``Downloader.run`` with mocked HTTP."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
import responses

import antenati
from antenati import Downloader, ProgressBar
from antenati import cli as antenati_cli
from tests.conftest import GALLERY_URL, MANIFEST_URL, TINY_JPEG


def _null_progress() -> ProgressBar:
    return ProgressBar(set_total=lambda _t: None, update=lambda: None)


def _image_url(canvas_label: str, size: int) -> str:
    base = f'https://iiif.example.org/iiif/img{canvas_label[-1]}'
    size_part = f'!{size},{size}' if size > 0 else 'pct:100'
    return f'{base}/full/{size_part}/0/default.jpg'


def _image_files(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir() if not path.name.startswith('.'))


@pytest.fixture
def downloader_in_tmp(downloader: Downloader, tmp_path: Path) -> Downloader:
    downloader.check_dir(parentdir=str(tmp_path), interactive=False)
    return downloader


def _register_jpegs(mocked_http, labels: tuple[str, ...], size: int = 0) -> None:
    for label in labels:
        mocked_http.add(responses.GET, _image_url(label, size), body=TINY_JPEG, status=200, content_type='image/jpeg')


def test_run_downloads_all_images_and_returns_consistent_report(mocked_http, downloader_in_tmp: Downloader) -> None:
    _register_jpegs(mocked_http, ('0001', '0002', '0003'))
    report = downloader_in_tmp.run(n_workers=2, size=0, progress=_null_progress())
    assert report.successful
    assert report.expected == report.attempted == report.completed == 3
    assert report.bytes_written == 3 * len(TINY_JPEG)
    assert _image_files(downloader_in_tmp.dirname) == ['0001.jpg', '0002.jpg', '0003.jpg']
    assert (downloader_in_tmp.dirname / '.antenati-manifest.json').is_file()
    index = json.loads((downloader_in_tmp.dirname / '.antenati-index.json').read_text(encoding='utf-8'))
    assert len(index['images']) == 3


def test_run_uses_constrained_size_urls(mocked_http, downloader_in_tmp: Downloader) -> None:
    size = 1234
    _register_jpegs(mocked_http, ('0001', '0002', '0003'), size)
    report = downloader_in_tmp.run(n_workers=2, size=size, progress=_null_progress())
    assert report.successful
    assert report.bytes_written == 3 * len(TINY_JPEG)


def test_run_partial_failure_is_structured_not_silent(mocked_http, downloader_in_tmp: Downloader) -> None:
    mocked_http.add(responses.GET, _image_url('0001', 0), body=TINY_JPEG, status=200, content_type='image/jpeg')
    mocked_http.add(responses.GET, _image_url('0002', 0), body='boom', status=500, content_type='text/plain')
    mocked_http.add(responses.GET, _image_url('0003', 0), body=TINY_JPEG, status=200, content_type='image/jpeg')
    report = downloader_in_tmp.run(n_workers=2, size=0, progress=_null_progress())
    assert not report.successful
    assert report.completed == 2
    assert len(report.failed) == 1
    assert report.failed[0].label == '0002'


def test_run_progress_callbacks_match_processed_pages(mocked_http, downloader_in_tmp: Downloader) -> None:
    _register_jpegs(mocked_http, ('0001', '0002', '0003'))
    totals: list[int] = []
    ticks = [0]

    def update() -> None:
        ticks[0] += 1

    report = downloader_in_tmp.run(n_workers=2, size=0, progress=ProgressBar(totals.append, update))
    assert report.successful
    assert totals == [3]
    assert ticks[0] == 3


def test_run_uses_validated_image_extension(mocked_http, tmp_path: Path) -> None:
    dl = Downloader(GALLERY_URL, first=0, last=1)
    dl.check_dir(parentdir=str(tmp_path), interactive=False)
    png = b'\x89PNG\r\n\x1a\n' + b'payload'
    mocked_http.add(responses.GET, _image_url('0001', 0), body=png, status=200, content_type='image/png')
    report = dl.run(n_workers=1, size=0, progress=_null_progress())
    assert report.successful
    assert (dl.dirname / '0001.png').is_file()


def test_run_with_first_last_range_downloads_subset(mocked_http, tmp_path: Path) -> None:
    dl = Downloader(GALLERY_URL, first=1, last=3)
    dl.check_dir(parentdir=str(tmp_path), interactive=False)
    _register_jpegs(mocked_http, ('0002', '0003'))
    report = dl.run(n_workers=2, size=0, progress=_null_progress())
    assert report.successful
    assert _image_files(dl.dirname) == ['0002.jpg', '0003.jpg']


def test_unknown_content_type_is_reported_as_failure(mocked_http, downloader_in_tmp: Downloader) -> None:
    for label in ('0001', '0002', '0003'):
        mocked_http.add(
            responses.GET,
            _image_url(label, 0),
            body=TINY_JPEG,
            status=200,
            content_type='application/x-no-such-format',
        )
    report = downloader_in_tmp.run(n_workers=2, size=0, progress=_null_progress())
    assert len(report.failed) == 3
    assert report.completed == 0


def test_run_cli_returns_same_structured_report(mocked_http, downloader_in_tmp: Downloader) -> None:
    _register_jpegs(mocked_http, ('0001', '0002', '0003'))
    report = antenati_cli.run_cli(downloader_in_tmp, n_workers=2, size=0)
    assert report.successful
    assert report.bytes_written == 3 * len(TINY_JPEG)


def test_progress_bar_dataclass_shape() -> None:
    bar = antenati.ProgressBar(set_total=lambda _t: None, update=lambda: None)
    assert callable(bar.set_total)
    assert callable(bar.update)


def test_run_honours_preset_cancel_event_without_image_requests(mocked_http, downloader_in_tmp: Downloader) -> None:
    _register_jpegs(mocked_http, ('0001', '0002', '0003'))
    calls_before = len(mocked_http.calls)
    cancel = threading.Event()
    cancel.set()
    report = downloader_in_tmp.run(n_workers=1, size=0, progress=_null_progress(), cancel=cancel)
    assert report.cancelled
    assert report.attempted == 0
    assert report.bytes_written == 0
    assert len(mocked_http.calls) == calls_before


def test_run_descriptive_names_embed_ark_and_image_ids(mocked_http, tmp_path: Path) -> None:
    dl = Downloader(GALLERY_URL, first=0, last=None, descriptive_names=True)
    dl.check_dir(parentdir=str(tmp_path), interactive=False)
    _register_jpegs(mocked_http, ('0001', '0002', '0003'))
    report = dl.run(n_workers=2, size=0, progress=_null_progress())
    assert report.successful
    assert _image_files(dl.dirname) == [
        '0001+an_ua19944535+img1.jpg',
        '0002+an_ua19944535+img2.jpg',
        '0003+an_ua19944535+img3.jpg',
    ]


def test_run_from_manifest_url_downloads_all_images(mocked_http, tmp_path: Path) -> None:
    dl = Downloader(MANIFEST_URL, first=0, last=None)
    dl.check_dir(parentdir=str(tmp_path), interactive=False)
    _register_jpegs(mocked_http, ('0001', '0002', '0003'))
    report = dl.run(n_workers=2, size=0, progress=_null_progress())
    assert report.successful
    assert _image_files(dl.dirname) == ['0001.jpg', '0002.jpg', '0003.jpg']
