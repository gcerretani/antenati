"""Focused unit tests for :mod:`antenati.http`."""

from __future__ import annotations

import pytest
import responses

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
            'https://example.org/ok',
            body='hi',
            status=200,
            content_type='text/plain',
        )
        reply = antenati_http.fetch(session, 'https://example.org/ok')
    assert reply.text == 'hi'


def test_fetch_raises_on_http_error() -> None:
    session = antenati_http.build_session()
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            'https://example.org/boom',
            body='nope',
            status=500,
            content_type='text/plain',
        )
        with pytest.raises(Exception):  # noqa: B017 - requests.HTTPError subclass
            antenati_http.fetch(session, 'https://example.org/boom')


def test_fetch_raises_on_waf_challenge() -> None:
    session = antenati_http.build_session()
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            'https://example.org/challenge',
            body='challenge',
            status=antenati_http.WAF_CHALLENGE_STATUS,
            headers={antenati_http.WAF_CHALLENGE_HEADER: antenati_http.WAF_CHALLENGE_VALUE},
            content_type='text/html; charset=utf-8',
        )
        with pytest.raises(WafChallengeError, match='AWS WAF challenge'):
            antenati_http.fetch(session, 'https://example.org/challenge')


def test_fetch_retries_on_503_then_succeeds() -> None:
    session = antenati_http.build_session()
    with responses.RequestsMock() as rsps:
        # urllib3's Retry consumes one response per attempt; queue two
        # transient failures followed by a success.
        rsps.add(
            responses.GET,
            'https://example.org/flaky',
            body='oops',
            status=503,
            content_type='text/plain',
        )
        rsps.add(
            responses.GET,
            'https://example.org/flaky',
            body='oops',
            status=503,
            content_type='text/plain',
        )
        rsps.add(
            responses.GET,
            'https://example.org/flaky',
            body='ok',
            status=200,
            content_type='text/plain',
        )
        reply = antenati_http.fetch(session, 'https://example.org/flaky')
    assert reply.status_code == 200
    assert reply.text == 'ok'


def test_session_mounts_retrying_adapter() -> None:
    session = antenati_http.build_session()
    adapter = session.get_adapter('https://example.org/')
    retry = adapter.max_retries
    assert retry.total == antenati_http.RETRY_TOTAL
    assert set(retry.status_forcelist) == set(antenati_http.RETRYABLE_STATUSES)


def test_fetch_does_not_treat_plain_202_as_waf() -> None:
    session = antenati_http.build_session()
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            'https://example.org/accepted',
            body='queued',
            status=202,
            content_type='text/plain',
        )
        reply = antenati_http.fetch(session, 'https://example.org/accepted')
    assert reply.status_code == 202
