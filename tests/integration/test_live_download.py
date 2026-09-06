"""Live integration tests against the real Portale Antenati.

These tests are slow, hit third-party services, and may fail when the
Antenati gallery frontend is under WAF challenge or when one of the IIIF
backends is unavailable. They are gated by the ``integration`` pytest
marker and excluded from the normal offline CI matrix.

The live workflow deliberately runs the gallery, direct-manifest and image
canaries as separate jobs. A gallery-page 403 must not hide whether the
manifest and image backends are still healthy.

To run locally::

    pytest -m integration
"""

from __future__ import annotations

from pathlib import Path

import pytest

from antenati import http, iiif
from antenati.downloader import Downloader, ProgressBar

# Gallery frontend canary. This page has been the project's smoke target
# since v2.5, but may be blocked for GitHub-hosted runners by the AWS WAF.
LIVE_GALLERY_URL = 'https://antenati.cultura.gov.it/ark:/12657/an_ua19944535/w9DWR8x'

# Direct IIIF backend canary. Keeping an explicit manifest URL is important:
# it lets CI check the storage/API layer even when the public gallery HTML is
# unreachable from the runner. The first canvas currently resolves to a real
# image on iiif-antenati.cultura.gov.it.
LIVE_MANIFEST_URL = 'https://dam-antenati.cultura.gov.it/antenati/containers/LzaxZkg/manifest'


def _null_progress() -> ProgressBar:
    return ProgressBar(set_total=lambda _t: None, update=lambda: None)


@pytest.mark.integration
def test_gallery_html_canary() -> None:
    """Check that the public gallery HTML is reachable and exposes a manifest."""
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
    """Check that the IIIF manifest backend works without using gallery HTML."""
    try:
        downloader = Downloader(LIVE_MANIFEST_URL, first=0, last=1)
    except Exception as exc:
        pytest.fail(f'direct manifest canary failed for {LIVE_MANIFEST_URL}: {exc!r}')

    assert downloader.gallery_length == 1
    assert downloader.canvases, 'direct manifest returned no canvases'


@pytest.mark.integration
def test_image_download_canary(tmp_path: Path) -> None:
    """Download one small image through the normal direct-manifest code path."""
    try:
        downloader = Downloader(LIVE_MANIFEST_URL, first=0, last=1)
        downloader.check_dir(parentdir=str(tmp_path), interactive=False)
        total = downloader.run(n_workers=1, size=200, progress=_null_progress())
    except Exception as exc:
        pytest.fail(f'image download canary failed via {LIVE_MANIFEST_URL}: {exc!r}')

    files = list(downloader.dirname.iterdir())
    assert len(files) == 1, f'expected exactly one downloaded image, got {[f.name for f in files]}'
    assert total > 0, 'image canary downloaded zero bytes'
