"""Tests for the IIIF gallery parsing path.

Covers ``__get_archive_id``, ``__get_iiif_manifest`` (including the manifest
URL regex on the gallery HTML), ``__get_content_type`` /
``__get_content_charset``, and the AWS WAF challenge detection in ``__get``.
"""

from __future__ import annotations

import pytest
import responses
from requests import Session

import antenati
from antenati import AntenatiDownloader
from tests.conftest import ARCHIVE_ID, GALLERY_URL, MANIFEST_URL

# Reach into the name-mangled private methods. These will become public
# pure functions in the upcoming refactor (PR-3); the indirection is
# intentionally ugly so the rename is impossible to miss.
_get_content_type = AntenatiDownloader._AntenatiDownloader__get_content_type  # type: ignore[attr-defined]
_get_content_charset = AntenatiDownloader._AntenatiDownloader__get_content_charset  # type: ignore[attr-defined]


def test_archive_id_is_extracted_from_url(downloader: AntenatiDownloader) -> None:
    assert downloader.archive_id == ARCHIVE_ID


def test_archive_id_raises_when_url_lacks_two_numbers(mocked_http) -> None:
    with pytest.raises(RuntimeError, match='Cannot get archive ID'):
        AntenatiDownloader('https://antenati.cultura.gov.it/no-numbers/', 0, None)


def test_manifest_is_loaded_from_gallery_html(downloader: AntenatiDownloader) -> None:
    assert downloader.manifest['@id'] == MANIFEST_URL
    assert len(downloader.manifest['sequences'][0]['canvases']) == 3


def test_gallery_url_is_recorded(downloader: AntenatiDownloader) -> None:
    assert downloader.url == GALLERY_URL


def test_canvases_are_sliced_by_first_last(mocked_http) -> None:
    dl = AntenatiDownloader(GALLERY_URL, first=1, last=2)
    assert dl.gallery_length == 1
    assert dl.canvases[0]['label'] == '0002'


def test_first_last_full_range(mocked_http) -> None:
    dl = AntenatiDownloader(GALLERY_URL, first=0, last=None)
    assert dl.gallery_length == 3


def test_no_manifest_line_raises(gallery_html: str) -> None:
    bad_html = '<html><body>no manifest here</body></html>'
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            GALLERY_URL,
            body=bad_html,
            status=200,
            content_type='text/html; charset=utf-8',
        )
        with pytest.raises(RuntimeError, match='No IIIF manifest found'):
            AntenatiDownloader(GALLERY_URL, 0, None)


def test_invalid_manifest_line_raises() -> None:
    # Has the keyword but no quoted URL: the regex still matches an empty
    # group, exposing the fragility the refactor will address. For now we
    # lock in the *current* behaviour so refactoring can't silently change
    # it.
    bad_html = '<script>var manifestId = noQuotesHere;</script>'
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            GALLERY_URL,
            body=bad_html,
            status=200,
            content_type='text/html; charset=utf-8',
        )
        with pytest.raises(Exception):  # noqa: B017 - locks current behaviour
            AntenatiDownloader(GALLERY_URL, 0, None)


def test_waf_challenge_is_detected() -> None:
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            GALLERY_URL,
            body='challenge',
            status=202,
            headers={'x-amzn-waf-action': 'challenge'},
            content_type='text/html; charset=utf-8',
        )
        with pytest.raises(RuntimeError, match='AWS WAF challenge'):
            AntenatiDownloader(GALLERY_URL, 0, None)


def test_get_content_type_strips_parameters() -> None:
    session = Session()
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            'https://example.org/x',
            body='ok',
            status=200,
            content_type='text/html; charset=utf-8',
        )
        reply = session.get('https://example.org/x')
    assert _get_content_type(reply) == 'text/html'


def test_get_content_charset() -> None:
    session = Session()
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            'https://example.org/x',
            body='ok',
            status=200,
            content_type='application/json; charset=utf-8',
        )
        reply = session.get('https://example.org/x')
    assert _get_content_charset(reply) == 'utf-8'


def test_default_thread_count_constant() -> None:
    assert antenati.DEFAULT_N_THREADS == 2


def test_default_size_constant() -> None:
    assert antenati.DEFAULT_SIZE == 0
