# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""HTTP plumbing for the Portale Antenati downloader."""

from __future__ import annotations

import logging
from email.message import Message

from requests import Response, Session
from requests.adapters import HTTPAdapter
from requests.utils import default_headers
from urllib3.util.retry import Retry

from antenati.errors import WafChallengeError

logger = logging.getLogger(__name__)

WAF_CHALLENGE_STATUS: int = 202
WAF_CHALLENGE_HEADER: str = 'x-amzn-waf-action'
WAF_CHALLENGE_VALUE: str = 'challenge'

RETRY_TOTAL: int = 5
RETRY_BACKOFF_FACTOR: float = 0.5
RETRYABLE_STATUSES: tuple[int, ...] = (429, 500, 502, 503, 504)

CONNECT_TIMEOUT_SECONDS: float = 10.0
READ_TIMEOUT_SECONDS: float = 60.0
DEFAULT_TIMEOUT: tuple[float, float] = (CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS)

_USER_AGENT: str = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'
)
_REFERER: str = 'https://antenati.cultura.gov.it/'


def _http_headers():
    headers = default_headers()
    headers['User-Agent'] = _USER_AGENT
    headers['Referer'] = _REFERER
    return headers


def _retry_policy() -> Retry:
    return Retry(
        total=RETRY_TOTAL,
        backoff_factor=RETRY_BACKOFF_FACTOR,
        status_forcelist=list(RETRYABLE_STATUSES),
        allowed_methods=frozenset(['GET']),
        raise_on_status=False,
    )


def build_session() -> Session:
    session = Session()
    session.headers = _http_headers()
    adapter = HTTPAdapter(max_retries=_retry_policy())
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session


def fetch(session: Session, url: str, *, stream: bool = False) -> Response:
    """GET ``url`` with retries/timeouts; optionally leave the body streamed."""
    logger.debug('GET %s', url)
    reply = session.get(url, timeout=DEFAULT_TIMEOUT, stream=stream)
    reply.raise_for_status()
    if reply.status_code == WAF_CHALLENGE_STATUS and reply.headers.get(WAF_CHALLENGE_HEADER) == WAF_CHALLENGE_VALUE:
        logger.warning('WAF challenge received from %s', reply.url)
        raise WafChallengeError(
            f'{reply.url}: AWS WAF challenge cannot be bypassed. '
            'Workaround: open the gallery page in a browser, copy the "IIIF manifest" link '
            'at the bottom of the left panel and pass that URL to this tool instead. '
            'See https://github.com/gcerretani/antenati/issues/25 for details.'
        )
    return reply


def get_content_type(reply: Response) -> str:
    """Return the bare content type or raise a controlled error if absent."""
    raw = reply.headers.get('Content-Type')
    if not raw:
        raise ValueError(f'{reply.url}: response has no Content-Type header')
    msg = Message()
    msg['Content-Type'] = raw
    return msg.get_content_type()


def get_content_charset(reply: Response) -> str | None:
    raw = reply.headers.get('Content-Type')
    if not raw:
        return None
    msg = Message()
    msg['Content-Type'] = raw
    return msg.get_content_charset()
