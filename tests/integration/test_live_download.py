"""Live integration tests against the real Portale Antenati.

The gallery frontend, direct manifest backend and image backend are checked
independently so a WAF failure does not hide the status of the IIIF layers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from antenati import http, iiif
from antenati.downloader import Downloader, ProgressBar

LIVE_GALLERY_URL = 'https://antenati.cultura.gov.it/ark:/12657/an_ua19944535/w9DWR8x'
LIVE_MANIFEST_URL = 'https://dam-antenati.cultura.gov.it/antenati/containers/LzaxZkg/manifest'


def _null_progress() -> ProgressBar:
    return ProgressBar(set_total=lambda _t: None, update=lambda: None)


@pytest.mark.integration
def test_gallery_html_canary() -> None:
    session = http.build_session()
    try:
        reply = http.fetch(session, LIVE_GALLERY_URL)
        charset = http.get_content_charset(reply) or 'utf-8'
        manifest_url = iiif.parse_manifest_url_from_html(reply.content.decode(charset), LIVE_GALLERY_URL)
    except Exception as exc:
        pytest.fail(f'gallery HTML canary failed for {LIVE_GALLERY_URL}: {exc!r}')
    assert manifest_url.startswith('https://'), f'gallery returned an invalid manifest URL: {manifest_url!r}'


@pytest.mark.integration
def test_direct_manifest_canary() -> None:
    try:
        downloader = Downloader(LIVE_MANIFEST_URL, first=0, last=1)
        downloader.load()
    except Exception as exc:
        pytest.fail(f'direct manifest canary failed for {LIVE_MANIFEST_URL}: {exc!r}')
    assert downloader.gallery_length == 1
    assert downloader.canvases, 'direct manifest returned no canvases'


@pytest.mark.integration
def test_image_download_canary(tmp_path: Path) -> None:
    try:
        downloader = Downloader(LIVE_MANIFEST_URL, first=0, last=1)
        downloader.check_dir(parentdir=str(tmp_path), interactive=False)
        report = downloader.run(n_workers=1, size=200, progress=_null_progress())
    except Exception as exc:
        pytest.fail(f'image download canary failed via {LIVE_MANIFEST_URL}: {exc!r}')

    images = [path for path in downloader.dirname.iterdir() if not path.name.startswith('.')]
    assert len(images) == 1, f'expected exactly one downloaded image, got {[path.name for path in images]}'
    assert report.successful, f'image canary incomplete: {report}'
    assert report.bytes_written > 0, 'image canary downloaded zero bytes'
