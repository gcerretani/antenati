from __future__ import annotations

from pathlib import Path

import responses

from antenati import Downloader, ProgressBar
from tests.conftest import GALLERY_URL, TINY_JPEG


def _null_progress() -> ProgressBar:
    return ProgressBar(set_total=lambda _t: None, update=lambda: None)


def _image_url(size: int = 0) -> str:
    size_part = f'!{size},{size}' if size > 0 else 'pct:100'
    return f'https://iiif.example.org/iiif/img1/full/{size_part}/0/default.jpg'


def _first_run(mocked_http, tmp_path: Path, size: int = 0) -> Downloader:
    downloader = Downloader(GALLERY_URL, first=0, last=1)
    downloader.check_dir(parentdir=str(tmp_path), interactive=False)
    mocked_http.add(responses.GET, _image_url(size), body=TINY_JPEG, status=200, content_type='image/jpeg')
    report = downloader.run(n_workers=1, size=size, progress=_null_progress())
    assert report.successful
    return downloader


def test_resume_skips_hash_verified_existing_file(mocked_http, tmp_path: Path) -> None:
    first = _first_run(mocked_http, tmp_path)
    resumed = Downloader(GALLERY_URL, first=0, last=1)
    resumed.load()
    resumed.dirname = first.dirname

    before_calls = len(mocked_http.calls)
    report = resumed.run(n_workers=1, size=0, progress=_null_progress(), resume=True)

    assert report.successful
    assert report.skipped == 1
    assert report.completed == 0
    assert len(mocked_http.calls) == before_calls


def test_resume_redownloads_corrupt_indexed_file(mocked_http, tmp_path: Path) -> None:
    first = _first_run(mocked_http, tmp_path)
    image_path = first.dirname / '0001.jpg'
    image_path.write_bytes(b'corrupt')

    resumed = Downloader(GALLERY_URL, first=0, last=1)
    resumed.load()
    resumed.dirname = first.dirname
    mocked_http.add(responses.GET, _image_url(), body=TINY_JPEG, status=200, content_type='image/jpeg')
    report = resumed.run(n_workers=1, size=0, progress=_null_progress(), resume=True)

    assert report.successful
    assert report.skipped == 0
    assert report.completed == 1
    assert image_path.read_bytes() == TINY_JPEG


def test_resume_does_not_reuse_different_resolution(mocked_http, tmp_path: Path) -> None:
    first = _first_run(mocked_http, tmp_path, size=0)
    resumed = Downloader(GALLERY_URL, first=0, last=1)
    resumed.load()
    resumed.dirname = first.dirname
    mocked_http.add(responses.GET, _image_url(200), body=TINY_JPEG, status=200, content_type='image/jpeg')

    report = resumed.run(n_workers=1, size=200, progress=_null_progress(), resume=True)

    assert report.skipped == 0
    assert report.completed == 1
