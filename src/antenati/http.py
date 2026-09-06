# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""HTTP plumbing for the Portale Antenati downloader.

Exposes a single small surface that the rest of the package leans on
without re-implementing the SAN-server quirks:

- :func:`build_session` returns a :class:`requests.Session` preconfigured
  with the browser-like headers required by the SAN reverse proxy and an
  ``urllib3.util.Retry`` adapter that transparently retries on transient
  5xx and rate-limit responses.
- :func:`fetch` performs a ``GET`` with bounded connect/read timeouts and
  turns the AWS WAF challenge response (HTTP 202 with
  ``x-amzn-waf-action: challenge``) into a typed
  :class:`antenati.errors.WafChallengeError`.
- :func:`get_content_type` / :func:`get_content_charset` parse a
  response's ``Content-Type`` header.
"""

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

# Requests interprets a two-tuple as (connect timeout, read timeout).  The
# read timeout is an inactivity timeout, not a total-transfer deadline, but
# it prevents a dead peer from keeping a worker blocked forever.
CONNECT_TIMEOUT_SECONDS: float = 10.0
READ_TIMEOUT_SECONDS: float = 60.0
DEFAULT_TIMEOUT: tuple[float, float] = (CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS)

_USER_AGENT: str = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'
_REFERER: str = 'https://antenati.cultura.gov.it/'


def _http_headers():
    """Build the header set required to reach the Portale Antenati."""
    headers = default_headers()
    headers['User-Agent'] = _USER_AGENT
    headers['Referer'] = _REFERER
    return headers


def _retry_policy() -> Retry:
    """Return the urllib3 Retry policy mounted on every Session."""
    return Retry(
        total=RETRY_TOTAL,
        backoff_factor=RETRY_BACKOFF_FACTOR,
        status_forcelist=list(RETRYABLE_STATUSES),
        allowed_methods=frozenset(['GET']),
        raise_on_status=False,
    )


def build_session() -> Session:
    """Return a Session preconfigured for Portale Antenati requests."""
    session = Session()
    session.headers = _http_headers()
    adapter = HTTPAdapter(max_retries=_retry_policy())
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session


def fetch(session: Session, url: str) -> Response:
    """GET ``url`` through ``session`` and turn known soft-failures into errors."""
    logger.debug('GET %s', url)
    reply = session.get(url, timeout=DEFAULT_TIMEOUT)
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
    """Return the bare content-type (no parameters) from a response."""
    msg = Message()
    msg['Content-Type'] = reply.headers['Content-Type']
    return msg.get_content_type()


def get_content_charset(reply: Response) -> str | None:
    """Return the charset declared in a response's Content-Type, if any."""
    msg = Message()
    msg['Content-Type'] = reply.headers['Content-Type']
    return msg.get_content_charset()
