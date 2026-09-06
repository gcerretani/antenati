# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure IIIF helpers for the Portale Antenati gallery format.

All functions in this module operate on plain Python values and perform no
network or filesystem I/O. Keeping parsing here makes Antenati/IIIF behavior
easy to test offline and lets :class:`antenati.downloader.Downloader` focus
on orchestration.

Malformed or unsupported manifest structures are reported through
:class:`antenati.errors.ManifestError`, so callers can distinguish parsing
problems from network and filesystem failures.
"""

from __future__ import annotations

from re import search
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from antenati.errors import ManifestError

# Gallery HTML embeds the IIIF manifest URL in a JavaScript `manifestId`
# assignment. Match that property specifically: taking the first URL found on
# the same line/page can select unrelated links and silently resolve the wrong
# resource.
_MANIFEST_ASSIGNMENT_PATTERN: str = r"""manifestId\s*[:=]\s*['"](https?://[^'"]+)['"]"""

# Antenati gallery ARKs encode the archive ID in an `an_ua<digits>` path
# component. Some direct manifest canvas IDs instead expose it as `iiif-<id>`.
# Parsing the URL path avoids confusing digits from schemes, ports or hosts.
_ARCHIVE_ID_PATTERN: str = r'/an_ua(\d+)(?:/|$)'
_CANVAS_ARCHIVE_ID_PATTERN: str = r'/iiif-(\d+)(?:/|$)'

# Metadata labels currently used by Portale Antenati to build the local
# directory name. Keeping them centralized documents the site-specific
# contract and makes future schema changes easier to spot.
META_CONTEXT: str = 'Contesto archivistico'
META_TITLE: str = 'Titolo'
META_TYPOLOGY: str = 'Tipologia'


def is_manifest_url(url: str) -> bool:
    """Return True when ``url`` points directly to a IIIF manifest.

    Direct manifest URLs are accepted as a first-class input because they
    avoid the gallery HTML/WAF layer and are also useful for automation.
    """
    return urlsplit(url).path.rstrip('/').endswith('/manifest')


def get_archive_id_from_url(url: str) -> str:
    """Return the numeric archive ID from an Antenati ``an_ua...`` path."""
    match = search(_ARCHIVE_ID_PATTERN, urlsplit(url).path)
    if not match:
        raise ManifestError(f'Cannot get archive ID from {url}')
    return match.group(1)


def get_archive_id_from_canvases(canvases: list[dict[str, Any]]) -> str:
    """Return the archive ID from the first canvas ``@id`` URL.

    This is the fallback used for direct manifest inputs, where the original
    URL may not contain the archive ID even though the canvas identifiers do.
    """
    try:
        canonical_url = canvases[0]['@id']
    except (KeyError, IndexError, TypeError) as exc:
        raise ManifestError("Canvas has no '@id' field") from exc
    path = urlsplit(canonical_url).path
    match = search(_ARCHIVE_ID_PATTERN, path) or search(_CANVAS_ARCHIVE_ID_PATTERN, path)
    if not match:
        raise ManifestError(f'Cannot get archive ID from {canonical_url}')
    return match.group(1)


def get_ark_id_from_url(url: str) -> str | None:
    """Return the ``an_...`` ARK token embedded in a URL, if any."""
    match = search(r'an_\w+', urlsplit(url).path)
    return match.group(0) if match else None


def get_image_id_from_url(url: str) -> str:
    """Return the IIIF image identifier from an Image API URL.

    A IIIF Image API request ends with
    ``/{identifier}/{region}/{size}/{rotation}/{quality}.{format}``, so the
    identifier is the fifth path component from the end for the URL forms
    supported by Antenati.
    """
    parts = urlsplit(url).path.split('/')
    if len(parts) < 5:
        raise ManifestError(f'Cannot get image ID from {url}')
    return parts[-5]


def parse_manifest_url_from_html(html: str, source_url: str) -> str:
    """Extract the URL specifically assigned to ``manifestId``.

    Binding the URL to the property name is intentional: Antenati pages may
    contain several unrelated absolute URLs before the manifest declaration.
    """
    if 'manifestId' not in html:
        raise ManifestError(f'No IIIF manifest found at {source_url}')
    match = search(_MANIFEST_ASSIGNMENT_PATTERN, html)
    if not match:
        raise ManifestError(f'Invalid IIIF manifest line at {source_url}')
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
    """Return the canvases of the manifest sliced by ``first:last``.

    The current Antenati manifests use the IIIF Presentation v2-style
    ``sequences[0].canvases`` layout. Broader IIIF variants are intentionally
    handled separately rather than guessed here.
    """
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
    """Rewrite the size component of a IIIF Image API request URL.

    Do not rely on a literal ``/full/full/0/`` substring: valid source URLs
    may use other size tokens such as ``max``. For the Antenati Image API URL
    shapes supported here, the size component is the third segment from the
    end, immediately before rotation and ``quality.format``.

    ``size > 0`` requests a bounding box via ``!N,N``; ``size == 0`` keeps
    the historical full-resolution behavior by requesting ``pct:100``.
    """
    parsed = urlsplit(url)
    parts = parsed.path.split('/')
    # Preserve historical behavior for non Image-API URLs such as info.json.
    if len(parts) < 7:
        return url
    parts[-3] = f'!{size},{size}' if size > 0 else 'pct:100'
    return urlunsplit((parsed.scheme, parsed.netloc, '/'.join(parts), parsed.query, parsed.fragment))
