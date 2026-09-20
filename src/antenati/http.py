# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""HTTP plumbing and network trust policy for the Portale Antenati downloader."""

from __future__ import annotations

import logging
from email.message import Message
from enum import Enum
from ipaddress import ip_address
from urllib.parse import urljoin, urlsplit

from requests import Response, Session, TooManyRedirects
from requests.adapters import HTTPAdapter
from requests.utils import default_headers
from urllib3.util.retry import Retry

from antenati.errors import HttpMetadataError, UrlTrustError, WafChallengeError

logger = logging.getLogger(__name__)

WAF_CHALLENGE_STATUS: int = 202
WAF_CHALLENGE_HEADER: str = 'x-amzn-waf-action'
WAF_CHALLENGE_VALUE: str = 'challenge'

RETRY_TOTAL: int = 5
RETRY_BACKOFF_FACTOR: float = 0.5
RETRYABLE_STATUSES: tuple[int, ...] = (429, 500, 502, 503, 504)
MAX_REDIRECTS: int = 10

CONNECT_TIMEOUT_SECONDS: float = 10.0
READ_TIMEOUT_SECONDS: float = 60.0
DEFAULT_TIMEOUT: tuple[float, float] = (CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS)

_PUBLIC_PORTAL_HOST: str = 'antenati.cultura.gov.it'
_USER_AGENT: str = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'
_REFERER: str = f'https://{_PUBLIC_PORTAL_HOST}/'


class UrlRole(str, Enum):
    """How a network URL entered the trusted Antenati source chain."""

    GALLERY = 'gallery'
    MANIFEST = 'manifest'
    IMAGE = 'image'


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
    return session


def _validate_https_url(url: str, role: UrlRole) -> str:
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise UrlTrustError(f'{url!r}: malformed URL') from exc

    if parsed.scheme.lower() != 'https':
        raise UrlTrustError(f'{url}: {role.value} URLs must use HTTPS')
    if parsed.username is not None or parsed.password is not None:
        raise UrlTrustError(f'{url}: userinfo is not allowed in Antenati URLs')
    if not hostname:
        raise UrlTrustError(f'{url}: URL has no hostname')
    if port not in (None, 443):
        raise UrlTrustError(f'{url}: unexpected port {port}; only HTTPS port 443 is allowed')
    return hostname.lower().rstrip('.')


def _validate_public_resource_host(url: str, hostname: str) -> None:
    """Reject local/private destinations while allowing Antenati backend hosts to evolve."""
    if hostname == 'localhost' or hostname.endswith('.localhost') or hostname.endswith('.local'):
        raise UrlTrustError(f'{url}: local hostnames are not allowed for Antenati resources')
    try:
        address = ip_address(hostname)
    except ValueError:
        if '.' not in hostname:
            raise UrlTrustError(f'{url}: single-label hostnames are not allowed for Antenati resources')
    else:
        if not address.is_global:
            raise UrlTrustError(f'{url}: non-public IP destinations are not allowed for Antenati resources')


def validate_url(url: str, role: UrlRole) -> None:
    """Validate a URL according to where it appears in the Antenati trust chain.

    Gallery URLs are the public user-facing contract and must remain on the
    Portale Antenati origin. Manifest and image URLs are discovered from
    already trusted Antenati content (or explicitly pasted as a direct
    manifest), so their backend hostnames are intentionally not hardcoded.
    They must still be HTTPS public-network destinations.
    """
    hostname = _validate_https_url(url, role)
    if role is UrlRole.GALLERY:
        if hostname != _PUBLIC_PORTAL_HOST:
            raise UrlTrustError(f'{url}: untrusted gallery host {hostname!r}; expected {_PUBLIC_PORTAL_HOST}')
        return
    _validate_public_resource_host(url, hostname)


def fetch(session: Session, url: str, *, role: UrlRole, stream: bool = False) -> Response:
    """GET a trusted resource, validating every redirect before following it."""
    current_url = url
    for redirect_count in range(MAX_REDIRECTS + 1):
        validate_url(current_url, role)
        logger.debug('GET %s', current_url)
        reply = session.get(current_url, timeout=DEFAULT_TIMEOUT, stream=stream, allow_redirects=False)
        try:
            if reply.is_redirect:
                location = reply.headers.get('Location')
                if not location:
                    raise UrlTrustError(f'{current_url}: redirect response has no Location header')
                if redirect_count >= MAX_REDIRECTS:
                    raise TooManyRedirects(f'Exceeded {MAX_REDIRECTS} redirects for {url}')
                target_url = urljoin(current_url, location.strip())
                validate_url(target_url, role)
                reply.close()
                current_url = target_url
                continue

            reply.raise_for_status()
            if reply.status_code == WAF_CHALLENGE_STATUS and reply.headers.get(WAF_CHALLENGE_HEADER) == WAF_CHALLENGE_VALUE:
                logger.warning('WAF challenge received from %s', reply.url)
                raise WafChallengeError(
                    f'{reply.url}: AWS WAF challenge cannot be bypassed. '
                    'Workaround: open the gallery page in a browser, copy the "IIIF manifest" link '
                    'at the bottom of the left panel and pass that URL to this tool instead. '
                    'See https://github.com/gcerretani/antenati/issues/25 for details.'
                )
        except Exception:
            reply.close()
            raise
        return reply

    raise TooManyRedirects(f'Exceeded {MAX_REDIRECTS} redirects for {url}')


def get_content_type(reply: Response) -> str:
    raw = reply.headers.get('Content-Type')
    if not raw:
        raise HttpMetadataError(f'{reply.url}: response has no Content-Type header')
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
