from __future__ import annotations

import json
from pathlib import Path

import pytest
import responses

from antenati import Downloader, ProgressBar
from antenati.provenance import INDEX_FILENAME
from tests.conftest import GALLERY_URL, TINY_JPEG


def _null_progress() -> ProgressBar:
    return ProgressBar(set_total=lambda _t: None, update=lambda: None)


def _image_url(size: int = 0) -> str:
    size_part = f'!{size},{size}' if size > 0 else 'pct:100'
    return f'https://iiif-antenati.cultura.gov.it/iiif/img1/full/{size_part}/0/default.jpg'


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


def test_resume_preserves_provenance_outside_requested_range(mocked_http, tmp_path: Path) -> None:
    full = Downloader(GALLERY_URL, first=0, last=None)
    full.check_dir(parentdir=str(tmp_path), interactive=False)
    for n in (1, 2, 3):
        mocked_http.add(
            responses.GET,
            f'https://iiif-antenati.cultura.gov.it/iiif/img{n}/full/pct:100/0/default.jpg',
            body=TINY_JPEG,
            status=200,
            content_type='image/jpeg',
        )
    report = full.run(n_workers=1, size=0, progress=_null_progress())
    assert report.successful

    narrow = Downloader(GALLERY_URL, first=1, last=2)
    narrow.load()
    narrow.dirname = full.dirname
    before_calls = len(mocked_http.calls)

    report = narrow.run(n_workers=1, size=0, progress=_null_progress(), resume=True)

    assert report.successful
    assert report.skipped == 1
    assert len(mocked_http.calls) == before_calls

    index = json.loads((full.dirname / INDEX_FILENAME).read_text(encoding='utf-8'))
    filenames = {record['filename'] for record in index['images']}
    assert filenames == {'0001.jpg', '0002.jpg', '0003.jpg'}


def test_resume_renames_verified_file_when_descriptive_names_changes(mocked_http, tmp_path: Path) -> None:
    first = _first_run(mocked_http, tmp_path)
    old_path = first.dirname / '0001.jpg'

    resumed = Downloader(GALLERY_URL, first=0, last=1, descriptive_names=True)
    resumed.load()
    resumed.dirname = first.dirname
    before_calls = len(mocked_http.calls)

    report = resumed.run(n_workers=1, size=0, progress=_null_progress(), resume=True)

    new_path = first.dirname / '0001+an_ua19944535+img1.jpg'
    assert report.successful
    assert report.skipped == 1
    assert len(mocked_http.calls) == before_calls
    assert not old_path.exists()
    assert new_path.read_bytes() == TINY_JPEG
    index = json.loads((first.dirname / INDEX_FILENAME).read_text(encoding='utf-8'))
    assert index['images'][0]['filename'] == new_path.name


def test_resume_renames_verified_file_back_to_default_names(mocked_http, tmp_path: Path) -> None:
    first = Downloader(GALLERY_URL, first=0, last=1, descriptive_names=True)
    first.check_dir(parentdir=str(tmp_path), interactive=False)
    mocked_http.add(responses.GET, _image_url(), body=TINY_JPEG, status=200, content_type='image/jpeg')
    assert first.run(n_workers=1, size=0, progress=_null_progress()).successful
    old_path = first.dirname / '0001+an_ua19944535+img1.jpg'

    resumed = Downloader(GALLERY_URL, first=0, last=1)
    resumed.load()
    resumed.dirname = first.dirname
    before_calls = len(mocked_http.calls)

    report = resumed.run(n_workers=1, size=0, progress=_null_progress(), resume=True)

    new_path = first.dirname / '0001.jpg'
    assert report.successful
    assert report.skipped == 1
    assert len(mocked_http.calls) == before_calls
    assert not old_path.exists()
    assert new_path.read_bytes() == TINY_JPEG


def test_resume_refuses_filename_reconciliation_collision(mocked_http, tmp_path: Path) -> None:
    first = _first_run(mocked_http, tmp_path)
    target = first.dirname / '0001+an_ua19944535+img1.jpg'
    target.write_bytes(b'unrelated')

    resumed = Downloader(GALLERY_URL, first=0, last=1, descriptive_names=True)
    resumed.load()
    resumed.dirname = first.dirname

    with pytest.raises(RuntimeError, match='target already exists'):
        resumed.run(n_workers=1, size=0, progress=_null_progress(), resume=True)

    assert (first.dirname / '0001.jpg').read_bytes() == TINY_JPEG
    assert target.read_bytes() == b'unrelated'
