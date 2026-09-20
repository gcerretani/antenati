"""Focused unit tests for :mod:`antenati.http`."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import responses
from requests import Response

from antenati import http as antenati_http
from antenati.errors import WafChallengeError


def test_build_session_sets_required_headers() -> None:
    session = antenati_http.build_session()
    assert 'antenati.cultura.gov.it' in session.headers['Referer']
    assert 'Mozilla/5.0' in session.headers['User-Agent']


def test_fetch_returns_response_on_2xx() -> None:
    session = antenati_http.build_session()
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            'https://antenati.cultura.gov.it/ok',
            body='hi',
            status=200,
            content_type='text/plain',
        )
        reply = antenati_http.fetch(session, 'https://antenati.cultura.gov.it/ok', role=antenati_http.UrlRole.GALLERY)
    assert reply.text == 'hi'


def test_fetch_raises_on_http_error() -> None:
    session = antenati_http.build_session()
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            'https://antenati.cultura.gov.it/boom',
            body='nope',
            status=500,
            content_type='text/plain',
        )
        with pytest.raises(Exception):  # noqa: B017 - requests.HTTPError subclass
            antenati_http.fetch(session, 'https://antenati.cultura.gov.it/boom', role=antenati_http.UrlRole.GALLERY)


def test_fetch_closes_response_on_http_error() -> None:
    session = antenati_http.build_session()
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            'https://antenati.cultura.gov.it/boom-stream',
            body='nope',
            status=500,
            content_type='text/plain',
        )
        with patch.object(Response, 'close', autospec=True) as mock_close, pytest.raises(Exception):  # noqa: B017
            antenati_http.fetch(session, 'https://antenati.cultura.gov.it/boom-stream', role=antenati_http.UrlRole.GALLERY, stream=True)
    assert mock_close.called


def test_fetch_raises_on_waf_challenge() -> None:
    session = antenati_http.build_session()
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            'https://antenati.cultura.gov.it/challenge',
            body='challenge',
            status=antenati_http.WAF_CHALLENGE_STATUS,
            headers={antenati_http.WAF_CHALLENGE_HEADER: antenati_http.WAF_CHALLENGE_VALUE},
            content_type='text/html; charset=utf-8',
        )
        with pytest.raises(WafChallengeError, match='AWS WAF challenge'):
            antenati_http.fetch(session, 'https://antenati.cultura.gov.it/challenge', role=antenati_http.UrlRole.GALLERY)


def test_fetch_retries_on_503_then_succeeds() -> None:
    session = antenati_http.build_session()
    with responses.RequestsMock() as rsps:
        # urllib3's Retry consumes one response per attempt; queue two
        # transient failures followed by a success.
        rsps.add(
            responses.GET,
            'https://antenati.cultura.gov.it/flaky',
            body='oops',
            status=503,
            content_type='text/plain',
        )
        rsps.add(
            responses.GET,
            'https://antenati.cultura.gov.it/flaky',
            body='oops',
            status=503,
            content_type='text/plain',
        )
        rsps.add(
            responses.GET,
            'https://antenati.cultura.gov.it/flaky',
            body='ok',
            status=200,
            content_type='text/plain',
        )
        reply = antenati_http.fetch(session, 'https://antenati.cultura.gov.it/flaky', role=antenati_http.UrlRole.GALLERY)
    assert reply.status_code == 200
    assert reply.text == 'ok'


def test_session_mounts_retrying_adapter() -> None:
    session = antenati_http.build_session()
    adapter = session.get_adapter('https://antenati.cultura.gov.it/')
    retry = adapter.max_retries
    assert retry.total == antenati_http.RETRY_TOTAL
    assert set(retry.status_forcelist) == set(antenati_http.RETRYABLE_STATUSES)


def test_fetch_does_not_treat_plain_202_as_waf() -> None:
    session = antenati_http.build_session()
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            'https://antenati.cultura.gov.it/accepted',
            body='queued',
            status=202,
            content_type='text/plain',
        )
        reply = antenati_http.fetch(session, 'https://antenati.cultura.gov.it/accepted', role=antenati_http.UrlRole.GALLERY)
    assert reply.status_code == 202
