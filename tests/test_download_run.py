"""End-to-end tests for ``Downloader.run`` with mocked HTTP.

These tests are the main safety net: they exercise the full happy path
(gallery -> manifest -> per-image download -> filesystem writes) and a few
key failure modes so the upcoming refactor cannot regress them silently.
"""

from __future__ import annotations

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
    """Mirror ``__manipulate_url`` for the IIIF URL each canvas will fetch."""
    base = f'https://iiif.example.org/iiif/img{canvas_label[-1]}'
    size_part = f'!{size},{size}' if size > 0 else 'pct:100'
    return f'{base}/full/{size_part}/0/default.jpg'


@pytest.fixture
def downloader_in_tmp(downloader: Downloader, tmp_path: Path) -> Downloader:
    downloader.check_dir(parentdir=str(tmp_path), interactive=False)
    return downloader


def test_run_downloads_all_images_full_size(mocked_http, downloader_in_tmp: Downloader) -> None:
    for label in ('0001', '0002', '0003'):
        mocked_http.add(
            responses.GET,
            _image_url(label, 0),
            body=TINY_JPEG,
            status=200,
            content_type='image/jpeg',
        )
    total = downloader_in_tmp.run(n_workers=2, size=0, progress=_null_progress())
    assert total == 3 * len(TINY_JPEG)
    files = sorted(p.name for p in downloader_in_tmp.dirname.iterdir())
    assert files == ['0001.jpg', '0002.jpg', '0003.jpg']


def test_run_uses_constrained_size_urls(mocked_http, downloader_in_tmp: Downloader) -> None:
    size = 1234
    for label in ('0001', '0002', '0003'):
        mocked_http.add(
            responses.GET,
            _image_url(label, size),
            body=TINY_JPEG,
            status=200,
            content_type='image/jpeg',
        )
    total = downloader_in_tmp.run(n_workers=2, size=size, progress=_null_progress())
    assert total == 3 * len(TINY_JPEG)


def test_run_partial_failure_raises_with_summary(mocked_http, downloader_in_tmp: Downloader) -> None:
    # First image succeeds, second 500s, third succeeds.
    mocked_http.add(
        responses.GET,
        _image_url('0001', 0),
        body=TINY_JPEG,
        status=200,
        content_type='image/jpeg',
    )
    mocked_http.add(
        responses.GET,
        _image_url('0002', 0),
        body='boom',
        status=500,
        content_type='text/plain',
    )
    mocked_http.add(
        responses.GET,
        _image_url('0003', 0),
        body=TINY_JPEG,
        status=200,
        content_type='image/jpeg',
    )
    with pytest.raises(RuntimeError, match=r'Failed to download 1 image'):
        downloader_in_tmp.run(n_workers=2, size=0, progress=_null_progress())


def test_run_progress_callbacks_are_invoked(mocked_http, downloader_in_tmp: Downloader) -> None:
    for label in ('0001', '0002', '0003'):
        mocked_http.add(
            responses.GET,
            _image_url(label, 0),
            body=TINY_JPEG,
            status=200,
            content_type='image/jpeg',
        )
    set_total_calls: list[int] = []
    update_count = [0]

    def _update() -> None:
        update_count[0] += 1

    progress = ProgressBar(set_total=set_total_calls.append, update=_update)
    downloader_in_tmp.run(n_workers=2, size=0, progress=progress)
    assert set_total_calls == [3]
    assert update_count[0] == 3


def test_run_filename_uses_image_extension(mocked_http, tmp_path: Path) -> None:
    # Construct a downloader with a single canvas served as PNG so we can
    # observe ``guess_extension`` picking up a different extension.
    dl = Downloader(GALLERY_URL, first=0, last=1)
    dl.check_dir(parentdir=str(tmp_path), interactive=False)
    mocked_http.add(
        responses.GET,
        _image_url('0001', 0),
        body=TINY_JPEG,  # bytes are irrelevant, content-type drives extension
        status=200,
        content_type='image/png',
    )
    dl.run(n_workers=1, size=0, progress=_null_progress())
    assert (dl.dirname / '0001.png').is_file()


def test_run_with_first_last_range_downloads_subset(mocked_http, tmp_path: Path) -> None:
    dl = Downloader(GALLERY_URL, first=1, last=3)
    dl.check_dir(parentdir=str(tmp_path), interactive=False)
    for label in ('0002', '0003'):
        mocked_http.add(
            responses.GET,
            _image_url(label, 0),
            body=TINY_JPEG,
            status=200,
            content_type='image/jpeg',
        )
    dl.run(n_workers=2, size=0, progress=_null_progress())
    files = sorted(p.name for p in dl.dirname.iterdir())
    assert files == ['0002.jpg', '0003.jpg']


def test_run_unknown_content_type_is_reported_as_failure(mocked_http, downloader_in_tmp: Downloader) -> None:
    # All three respond with a content-type ``guess_extension`` cannot map.
    for label in ('0001', '0002', '0003'):
        mocked_http.add(
            responses.GET,
            _image_url(label, 0),
            body=TINY_JPEG,
            status=200,
            content_type='application/x-no-such-format',
        )
    with pytest.raises(RuntimeError, match=r'Failed to download 3 image'):
        downloader_in_tmp.run(n_workers=2, size=0, progress=_null_progress())


def test_run_cli_uses_tqdm_progress_bar(mocked_http, downloader_in_tmp: Downloader) -> None:
    for label in ('0001', '0002', '0003'):
        mocked_http.add(
            responses.GET,
            _image_url(label, 0),
            body=TINY_JPEG,
            status=200,
            content_type='image/jpeg',
        )
    total = antenati_cli.run_cli(downloader_in_tmp, n_workers=2, size=0)
    assert total == 3 * len(TINY_JPEG)


def test_progress_bar_dataclass_shape() -> None:
    bar = antenati.ProgressBar(set_total=lambda _t: None, update=lambda: None)
    assert callable(bar.set_total)
    assert callable(bar.update)


def test_run_honours_preset_cancel_event(mocked_http, downloader_in_tmp: Downloader) -> None:
    # Register all canvases as 200s; with cancel already set when run()
    # starts, no fetch should be attempted and the total bytes returned
    # must be zero. The mock is created with assert_all_requests_are_fired
    # = False so unused registrations don't fail the test.
    for label in ('0001', '0002', '0003'):
        mocked_http.add(
            responses.GET,
            _image_url(label, 0),
            body=TINY_JPEG,
            status=200,
            content_type='image/jpeg',
        )
    cancel = threading.Event()
    cancel.set()
    total = downloader_in_tmp.run(n_workers=1, size=0, progress=_null_progress(), cancel=cancel)
    assert total == 0


def test_run_descriptive_names_embed_ark_and_image_ids(mocked_http, tmp_path: Path) -> None:
    dl = Downloader(GALLERY_URL, first=0, last=None, descriptive_names=True)
    dl.check_dir(parentdir=str(tmp_path), interactive=False)
    for label in ('0001', '0002', '0003'):
        mocked_http.add(
            responses.GET,
            _image_url(label, 0),
            body=TINY_JPEG,
            status=200,
            content_type='image/jpeg',
        )
    dl.run(n_workers=2, size=0, progress=_null_progress())
    files = sorted(p.name for p in dl.dirname.iterdir())
    assert files == [
        '0001+an_ua19944535+img1.jpg',
        '0002+an_ua19944535+img2.jpg',
        '0003+an_ua19944535+img3.jpg',
    ]


def test_run_from_manifest_url_downloads_all_images(mocked_http, tmp_path: Path) -> None:
    dl = Downloader(MANIFEST_URL, first=0, last=None)
    dl.check_dir(parentdir=str(tmp_path), interactive=False)
    for label in ('0001', '0002', '0003'):
        mocked_http.add(
            responses.GET,
            _image_url(label, 0),
            body=TINY_JPEG,
            status=200,
            content_type='image/jpeg',
        )
    total = dl.run(n_workers=2, size=0, progress=_null_progress())
    assert total == 3 * len(TINY_JPEG)
    files = sorted(p.name for p in dl.dirname.iterdir())
    assert files == ['0001.jpg', '0002.jpg', '0003.jpg']
