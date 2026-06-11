"""Tests for the IIIF gallery parsing path.

Exercises both the pure helpers in :mod:`antenati.iiif` /
:mod:`antenati.http` and the orchestration in
:class:`antenati.Downloader`.
"""

from __future__ import annotations

import pytest
import responses
from requests import Session

import antenati
from antenati import Downloader
from antenati import http as antenati_http
from antenati import iiif as antenati_iiif
from antenati.errors import ManifestError, WafChallengeError
from tests.conftest import ARCHIVE_ID, GALLERY_URL, MANIFEST_URL


def test_archive_id_is_extracted_from_url(downloader: Downloader) -> None:
    assert downloader.archive_id == ARCHIVE_ID


def test_archive_id_helper_returns_second_integer() -> None:
    assert antenati_iiif.get_archive_id_from_url(GALLERY_URL) == ARCHIVE_ID


def test_archive_id_helper_raises_when_url_lacks_two_numbers() -> None:
    with pytest.raises(ManifestError, match='Cannot get archive ID'):
        antenati_iiif.get_archive_id_from_url('https://antenati.cultura.gov.it/no-numbers/')


def test_constructor_raises_when_url_lacks_two_numbers(mocked_http) -> None:
    with pytest.raises(ManifestError, match='Cannot get archive ID'):
        Downloader('https://antenati.cultura.gov.it/no-numbers/', 0, None)


def test_manifest_is_loaded_from_gallery_html(downloader: Downloader) -> None:
    assert downloader.manifest['@id'] == MANIFEST_URL
    assert len(downloader.manifest['sequences'][0]['canvases']) == 3


def test_gallery_url_is_recorded(downloader: Downloader) -> None:
    assert downloader.url == GALLERY_URL


def test_canvases_are_sliced_by_first_last(mocked_http) -> None:
    dl = Downloader(GALLERY_URL, first=1, last=2)
    assert dl.gallery_length == 1
    assert dl.canvases[0]['label'] == '0002'


def test_first_last_full_range(mocked_http) -> None:
    dl = Downloader(GALLERY_URL, first=0, last=None)
    assert dl.gallery_length == 3


def test_parse_manifest_url_from_html_extracts_quoted_url() -> None:
    html = "<script>var manifestId = 'https://example.org/m';</script>"
    assert antenati_iiif.parse_manifest_url_from_html(html, 'src') == 'https://example.org/m'


def test_parse_manifest_url_no_keyword_raises() -> None:
    with pytest.raises(ManifestError, match='No IIIF manifest found'):
        antenati_iiif.parse_manifest_url_from_html('<html>nothing here</html>', 'src')


@pytest.mark.parametrize(
    'html',
    [
        # Single quotes around a URL with underscores and a query string.
        "<script>var manifestId = 'https://iiif.example.org/ark:/12657/an_ua19944535/manifest?v=2';</script>",
        # Double quotes.
        '<script>var manifestId = "https://iiif.example.org/manifest";</script>',
    ],
)
def test_parse_manifest_url_accepts_modern_url_shapes(html: str) -> None:
    # Locks the post-hardening behaviour: the legacy regex rejected
    # underscores and query strings, the new one accepts them.
    result = antenati_iiif.parse_manifest_url_from_html(html, 'src')
    assert result.startswith('https://')


def test_constructor_raises_when_html_lacks_manifest(gallery_html: str) -> None:
    bad_html = '<html><body>no manifest here</body></html>'
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            GALLERY_URL,
            body=bad_html,
            status=200,
            content_type='text/html; charset=utf-8',
        )
        with pytest.raises(ManifestError, match='No IIIF manifest found'):
            Downloader(GALLERY_URL, 0, None)


def test_constructor_raises_on_invalid_manifest_line() -> None:
    # The ``manifestId`` keyword is present but there is no quoted URL on
    # the line: parsing must raise a typed ManifestError.
    bad_html = '<script>var manifestId = noQuotesHere;</script>'
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            GALLERY_URL,
            body=bad_html,
            status=200,
            content_type='text/html; charset=utf-8',
        )
        with pytest.raises(ManifestError, match='Invalid IIIF manifest line'):
            Downloader(GALLERY_URL, 0, None)


def test_waf_challenge_is_detected() -> None:
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            GALLERY_URL,
            body='challenge',
            status=antenati_http.WAF_CHALLENGE_STATUS,
            headers={antenati_http.WAF_CHALLENGE_HEADER: antenati_http.WAF_CHALLENGE_VALUE},
            content_type='text/html; charset=utf-8',
        )
        with pytest.raises(WafChallengeError, match='AWS WAF challenge'):
            Downloader(GALLERY_URL, 0, None)


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
    assert antenati_http.get_content_type(reply) == 'text/html'


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
    assert antenati_http.get_content_charset(reply) == 'utf-8'


def test_default_thread_count_constant() -> None:
    assert antenati.DEFAULT_N_THREADS == 2


def test_default_size_constant() -> None:
    assert antenati.DEFAULT_SIZE == 0


def test_is_manifest_url_detects_manifest_paths() -> None:
    assert antenati_iiif.is_manifest_url('https://dam-antenati.cultura.gov.it/antenati/containers/0ADVMr3/manifest')
    assert antenati_iiif.is_manifest_url(MANIFEST_URL)
    assert antenati_iiif.is_manifest_url(MANIFEST_URL + '/')
    assert not antenati_iiif.is_manifest_url(GALLERY_URL)


def test_archive_id_is_recovered_from_canvases(manifest_dict: dict) -> None:
    canvases = manifest_dict['sequences'][0]['canvases']
    assert antenati_iiif.get_archive_id_from_canvases(canvases) == ARCHIVE_ID


def test_archive_id_from_canvases_raises_on_missing_id() -> None:
    with pytest.raises(ManifestError, match="Canvas has no '@id'"):
        antenati_iiif.get_archive_id_from_canvases([{'label': '0001'}])


def test_ark_id_is_extracted_from_gallery_url() -> None:
    assert antenati_iiif.get_ark_id_from_url(GALLERY_URL) == f'an_ua{ARCHIVE_ID}'


def test_ark_id_is_none_when_absent() -> None:
    assert antenati_iiif.get_ark_id_from_url(MANIFEST_URL) is None


def test_image_id_is_extracted_from_iiif_image_url() -> None:
    url = 'https://iiif-antenati.cultura.gov.it/iiif/2/5gGAbBp/full/full/0/default.jpg'
    assert antenati_iiif.get_image_id_from_url(url) == '5gGAbBp'


def test_image_id_raises_on_short_path() -> None:
    with pytest.raises(ManifestError, match='Cannot get image ID'):
        antenati_iiif.get_image_id_from_url('https://example.org/too/short')


def test_downloader_accepts_manifest_url_directly(mocked_http) -> None:
    # The gallery page is never fetched: only the manifest URL is hit.
    # This is the workaround for galleries behind the AWS WAF challenge
    # (https://github.com/gcerretani/antenati/issues/25).
    dl = Downloader(MANIFEST_URL, first=0, last=None)
    assert dl.archive_id == ARCHIVE_ID
    assert dl.gallery_length == 3
    requested = [call.request.url for call in mocked_http.calls]
    assert requested == [MANIFEST_URL]
