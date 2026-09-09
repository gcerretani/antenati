from __future__ import annotations

from pathlib import Path

import pytest
import responses

from antenati import ProgressBar
from antenati.downloader import Downloader, DownloadLimits
from antenati.errors import ResourceLimitError
from tests.conftest import GALLERY_URL, TINY_JPEG


def _null_progress() -> ProgressBar:
    return ProgressBar(set_total=lambda _t: None, update=lambda: None)


def test_manifest_canvas_limit_fails_before_image_execution(mocked_http) -> None:
    downloader = Downloader(GALLERY_URL, first=0, last=None, limits=DownloadLimits(max_canvases=2))
    with pytest.raises(ResourceLimitError, match='3 canvases'):
        downloader.load()


def test_oversized_image_is_rejected_without_final_file(mocked_http, tmp_path: Path) -> None:
    limits = DownloadLimits(max_image_bytes=len(TINY_JPEG) - 1)
    downloader = Downloader(GALLERY_URL, first=0, last=1, limits=limits)
    downloader.check_dir(parentdir=str(tmp_path), interactive=False)
    mocked_http.add(
        responses.GET,
        'https://iiif.example.org/iiif/img1/full/pct:100/0/default.jpg',
        body=TINY_JPEG,
        status=200,
        content_type='image/jpeg',
    )

    report = downloader.run(n_workers=1, size=0, progress=_null_progress())
    assert len(report.failed) == 1
    assert 'image exceeded' in report.failed[0].reason
    assert not (downloader.dirname / '0001.jpg').exists()


def test_in_flight_window_scales_with_workers_without_using_gallery_size() -> None:
    downloader = Downloader('https://example.invalid/manifest', 0, None, limits=DownloadLimits(in_flight_factor=2))
    assert downloader._in_flight_limit(1) == 2
    assert downloader._in_flight_limit(4) == 8


def test_failed_image_bytes_are_refunded_to_total_budget(mocked_http, tmp_path: Path) -> None:
    corrupt_body = b'\x00' * 20
    limits = DownloadLimits(max_total_bytes=len(corrupt_body))
    downloader = Downloader(GALLERY_URL, first=0, last=2, limits=limits)
    downloader.check_dir(parentdir=str(tmp_path), interactive=False)
    mocked_http.add(
        responses.GET,
        'https://iiif.example.org/iiif/img1/full/pct:100/0/default.jpg',
        body=corrupt_body,
        status=200,
        content_type='image/jpeg',
    )
    mocked_http.add(
        responses.GET,
        'https://iiif.example.org/iiif/img2/full/pct:100/0/default.jpg',
        body=TINY_JPEG,
        status=200,
        content_type='image/jpeg',
    )

    report = downloader.run(n_workers=1, size=0, progress=_null_progress())

    assert len(report.failed) == 1
    assert report.completed == 1
    assert (downloader.dirname / '0002.jpg').read_bytes() == TINY_JPEG
