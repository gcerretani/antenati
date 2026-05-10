"""HTTP plumbing for the Portale Antenati downloader.

Exposes a single small surface that ``antenati.AntenatiDownloader`` (and any
future module) can lean on without re-implementing the SAN-server quirks:

- :func:`build_session` returns a :class:`requests.Session` preconfigured
  with the headers required by the SAN reverse proxy.
- :func:`fetch` performs a ``GET`` and turns the AWS WAF challenge response
  (HTTP 202 with ``x-amzn-waf-action: challenge``) into a clean
  :class:`RuntimeError`.
- :func:`get_content_type` / :func:`get_content_charset` parse a response's
  ``Content-Type`` header.

This module is intentionally side-effect free at import time: it only
declares helpers. Retry policies and structured logging will be added in a
later refactor step.
"""

from __future__ import annotations

from email.message import Message
from typing import Optional

from requests import Response, Session
from requests.utils import default_headers

# These are observable behaviours of the SAN server; pulling them into
# named constants makes the WAF detection explicit and lets tests assert
# against the contract instead of magic strings.
WAF_CHALLENGE_STATUS: int = 202
WAF_CHALLENGE_HEADER: str = 'x-amzn-waf-action'
WAF_CHALLENGE_VALUE: str = 'challenge'

# Mimic a current Edge-on-Windows fingerprint. The SAN reverse proxy 403s
# requests that look automated, so this header is part of the contract.
_USER_AGENT: str = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'
_REFERER: str = 'https://antenati.cultura.gov.it/'


def _http_headers():
    """Build the header set required to reach the Portale Antenati."""
    headers = default_headers()
    headers['User-Agent'] = _USER_AGENT
    headers['Referer'] = _REFERER
    return headers


def build_session() -> Session:
    """Return a Session preconfigured for Portale Antenati requests."""
    session = Session()
    session.headers = _http_headers()
    return session


def fetch(session: Session, url: str) -> Response:
    """GET ``url`` through ``session`` and turn known soft-failures into errors.

    Raises
    ------
    requests.HTTPError
        If the server returned a 4xx/5xx status.
    RuntimeError
        If the server returned an AWS WAF challenge (HTTP 202 with the
        ``x-amzn-waf-action: challenge`` header). There is currently no
        bypass; surfacing this as a distinct error helps callers diagnose
        the problem without parsing HTML.
    """
    reply = session.get(url)
    reply.raise_for_status()
    if reply.status_code == WAF_CHALLENGE_STATUS and reply.headers.get(WAF_CHALLENGE_HEADER) == WAF_CHALLENGE_VALUE:
        raise RuntimeError(f'{reply.url}: AWS WAF challenge cannot be bypassed. See https://github.com/gcerretani/antenati/issues/25 for details.')
    return reply


def get_content_type(reply: Response) -> str:
    """Return the bare content-type (no parameters) from a response."""
    msg = Message()
    msg['Content-Type'] = reply.headers['Content-Type']
    return msg.get_content_type()


def get_content_charset(reply: Response) -> Optional[str]:
    """Return the charset declared in a response's Content-Type, if any."""
    msg = Message()
    msg['Content-Type'] = reply.headers['Content-Type']
    return msg.get_content_charset()
