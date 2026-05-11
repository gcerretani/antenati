"""Shared test fixtures.

The HTML and IIIF JSON fixtures under ``tests/fixtures/`` mirror the shape
of the responses served by the real Portale Antenati but contain no real
data. They let us exercise the parsing, URL manipulation and download
orchestration of :class:`antenati.Downloader` entirely offline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import responses as responses_module

import antenati

FIXTURES_DIR = Path(__file__).parent / 'fixtures'

# A real-shaped gallery URL: ``__get_archive_id`` extracts the second
# integer it finds, so we must keep at least two numbers in the path.
GALLERY_URL = 'https://antenati.cultura.gov.it/ark:/12657/an_ua19944535/gallery'
ARCHIVE_ID = '19944535'

# The HTML fixture embeds this exact manifest URL inside a ``manifestId``
# JavaScript assignment.
MANIFEST_URL = 'https://iiif.example.org/ark/12657/iiif-19944535/manifest'

# Tests don't decode the downloaded payload; any byte sequence is fine.
TINY_JPEG = b'\xff\xd8\xff\xd9'  # SOI + EOI (smallest "valid" JPEG)


@pytest.fixture
def gallery_html() -> str:
    return (FIXTURES_DIR / 'gallery.html').read_text(encoding='utf-8')


@pytest.fixture
def manifest_dict() -> dict:
    with (FIXTURES_DIR / 'manifest_minimal.json').open(encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture
def manifest_text(manifest_dict: dict) -> str:
    return json.dumps(manifest_dict)


@pytest.fixture
def mocked_http(gallery_html: str, manifest_text: str):
    """Register HTTP mocks for the gallery page and the IIIF manifest.

    Image URLs are not registered here: each test adds the canvases it
    actually exercises so failures are easy to attribute.
    """
    with responses_module.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(
            responses_module.GET,
            GALLERY_URL,
            body=gallery_html,
            status=200,
            content_type='text/html; charset=utf-8',
        )
        rsps.add(
            responses_module.GET,
            MANIFEST_URL,
            body=manifest_text,
            status=200,
            content_type='application/json; charset=utf-8',
        )
        yield rsps


@pytest.fixture
def downloader(mocked_http) -> antenati.Downloader:
    """Build a Downloader against the mocked gallery+manifest."""
    return antenati.Downloader(GALLERY_URL, first=0, last=None)
