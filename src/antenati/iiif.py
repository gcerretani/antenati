# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure IIIF helpers for the Portale Antenati gallery format."""

from __future__ import annotations

from re import search
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from antenati.errors import ManifestError

_MANIFEST_ASSIGNMENT_PATTERN: str = r"""manifestId\s*[:=]\s*['"](https?://[^'"]+)['"]"""
_ARCHIVE_ID_PATTERN: str = r'/an_ua(\d+)(?:/|$)'

META_CONTEXT: str = 'Contesto archivistico'
META_TITLE: str = 'Titolo'
META_TYPOLOGY: str = 'Tipologia'


def is_manifest_url(url: str) -> bool:
    """Return True when ``url`` points directly to a IIIF manifest."""
    return urlsplit(url).path.rstrip('/').endswith('/manifest')


def get_archive_id_from_url(url: str) -> str:
    """Return the numeric archive ID from an Antenati ``an_ua...`` path."""
    match = search(_ARCHIVE_ID_PATTERN, urlsplit(url).path)
    if not match:
        raise ManifestError(f'Cannot get archive ID from {url}')
    return match.group(1)


def get_archive_id_from_canvases(canvases: list[dict[str, Any]]) -> str:
    """Return the archive ID from the first canvas ``@id`` URL."""
    try:
        canonical_url = canvases[0]['@id']
    except (KeyError, IndexError, TypeError) as exc:
        raise ManifestError("Canvas has no '@id' field") from exc
    return get_archive_id_from_url(canonical_url)


def get_ark_id_from_url(url: str) -> str | None:
    """Return the ``an_...`` ark token embedded in a URL, if any."""
    match = search(r'an_\w+', urlsplit(url).path)
    return match.group(0) if match else None


def get_image_id_from_url(url: str) -> str:
    """Return the IIIF image identifier from an Image API URL."""
    parts = urlsplit(url).path.split('/')
    if len(parts) < 5:
        raise ManifestError(f'Cannot get image ID from {url}')
    return parts[-5]


def parse_manifest_url_from_html(html: str, source_url: str) -> str:
    """Extract the URL specifically assigned to ``manifestId``."""
    match = search(_MANIFEST_ASSIGNMENT_PATTERN, html)
    if not match:
        raise ManifestError(f'No valid IIIF manifest found at {source_url}')
    return match.group(1)


def get_metadata_value(manifest: dict[str, Any], label: str) -> str:
    """Return the value of the ``label`` entry in a manifest's metadata."""
    try:
        entries = manifest['metadata']
    except KeyError as exc:
        raise ManifestError("Manifest has no 'metadata' field") from exc
    try:
        return next(i['value'] for i in entries if i['label'] == label)
    except StopIteration as exc:
        raise ManifestError(f'Cannot get {label} from manifest') from exc


def slice_canvases(manifest: dict[str, Any], first: int, last: int | None) -> list[dict[str, Any]]:
    """Return the canvases of the manifest sliced by ``first:last``."""
    try:
        canvases = manifest['sequences'][0]['canvases']
    except (KeyError, IndexError, TypeError) as exc:
        raise ManifestError("Manifest has no 'sequences[0].canvases' field") from exc
    if not canvases:
        raise ManifestError('Manifest contains no canvases')
    selected = canvases[first:last]
    if not selected:
        raise ManifestError('Selected canvas range is empty')
    return selected


def image_url_for_canvas(canvas: dict[str, Any]) -> str:
    """Return the image URL declared by an IIIF canvas."""
    try:
        return canvas['images'][0]['resource']['@id']
    except (KeyError, IndexError, TypeError) as exc:
        raise ManifestError("Canvas has no 'images[0].resource.@id' field") from exc


def manipulate_image_url(url: str, size: int) -> str:
    """Rewrite the size component of a IIIF Image API request URL."""
    parsed = urlsplit(url)
    parts = parsed.path.split('/')
    # Preserve historical behavior for non Image-API URLs such as info.json.
    if len(parts) < 7:
        return url
    parts[-3] = f'!{size},{size}' if size > 0 else 'pct:100'
    return urlunsplit((parsed.scheme, parsed.netloc, '/'.join(parts), parsed.query, parsed.fragment))
