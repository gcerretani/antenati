"""Pure IIIF helpers for the Portale Antenati gallery format.

All functions in this module work on plain Python data (strings, dicts).
None of them perform I/O, which makes them straightforward to unit test
offline. :class:`antenati.downloader.Downloader` orchestrates HTTP
fetching and delegates the parsing to these helpers.

Errors raised by this module are all subclasses of
:class:`antenati.errors.ManifestError`, so callers can catch one type to
distinguish "the gallery looks malformed" from network or filesystem
failures.
"""

from __future__ import annotations

from re import findall, search
from typing import Any

from antenati.errors import ManifestError

# The gallery HTML embeds the IIIF manifest URL inside a JavaScript
# ``manifestId = '<URL>'`` assignment. The pattern accepts both single
# and double quotes around the URL and is intentionally permissive about
# what characters are allowed inside the URL (anything that's not the
# closing quote) to survive future URL changes by the SAN team.
_MANIFEST_URL_PATTERN: str = r"""['"](https?://[^'"]+)['"]"""
_MANIFEST_KEYWORD: str = 'manifestId'

# IIIF size syntax: ``/full/full/0/`` is the legacy "give me everything"
# template baked into the manifest. We rewrite it to one of the size
# variants the SAN server still serves.
_FULL_SIZE_TEMPLATE: str = '/full/full/0/'

# Metadata labels we expect in every Antenati IIIF manifest.
META_CONTEXT: str = 'Contesto archivistico'
META_TITLE: str = 'Titolo'
META_TYPOLOGY: str = 'Tipologia'


def get_archive_id_from_url(url: str) -> str:
    """Return the archive ID embedded in a Portale Antenati gallery URL.

    Antenati gallery URLs contain at least two integers; the second one is
    the archive ID. Example::

        https://antenati.cultura.gov.it/ark:/12657/an_ua19944535/...
                                            ^^^^^ ^^^^^^^^
                                            ark   archive id
    """
    numbers = findall(r'(\d+)', url)
    if len(numbers) < 2:
        raise ManifestError(f'Cannot get archive ID from {url}')
    return numbers[1]


def parse_manifest_url_from_html(html: str, source_url: str) -> str:
    """Extract the IIIF manifest URL from a Portale Antenati gallery page.

    Parameters
    ----------
    html:
        The decoded HTML body of the gallery page.
    source_url:
        The URL the HTML came from. Only used to produce informative error
        messages -- this function performs no I/O.
    """
    manifest_line = next(
        (line for line in html.splitlines() if _MANIFEST_KEYWORD in line),
        None,
    )
    if not manifest_line:
        raise ManifestError(f'No IIIF manifest found at {source_url}')
    match = search(_MANIFEST_URL_PATTERN, manifest_line)
    if not match:
        raise ManifestError(f'Invalid IIIF manifest line found at {source_url}')
    return match.group(1)


def get_metadata_value(manifest: dict[str, Any], label: str) -> str:
    """Return the value of the ``label`` entry in a manifest's metadata.

    The IIIF manifest metadata is a list of ``{label, value}`` dicts.
    """
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

    Raises :class:`ManifestError` if the manifest is missing the expected
    ``sequences[0].canvases`` path or that path contains nothing.
    """
    try:
        canvases = manifest['sequences'][0]['canvases']
    except (KeyError, IndexError, TypeError) as exc:
        raise ManifestError("Manifest has no 'sequences[0].canvases' field") from exc
    if not canvases:
        raise ManifestError('Manifest contains no canvases')
    return canvases[first:last]


def image_url_for_canvas(canvas: dict[str, Any]) -> str:
    """Return the image URL declared by an IIIF canvas."""
    try:
        return canvas['images'][0]['resource']['@id']
    except (KeyError, IndexError, TypeError) as exc:
        raise ManifestError("Canvas has no 'images[0].resource.@id' field") from exc


def manipulate_image_url(url: str, size: int) -> str:
    """Rewrite an IIIF image URL to request a specific output size.

    The Portale Antenati SAN server currently 403s on ``/full/full/0/``
    (deprecated) and ``/full/max/0/``. Replace those with one of the
    variants that still works:

    - ``size > 0`` -> ``/full/!{size},{size}/0/`` (constrain by box)
    - ``size == 0`` -> ``/full/pct:100/0/`` (full resolution, current
      working alternative)
    """
    size_str = f'/full/!{size},{size}/0/' if size > 0 else '/full/pct:100/0/'
    return url.replace(_FULL_SIZE_TEMPLATE, size_str)
