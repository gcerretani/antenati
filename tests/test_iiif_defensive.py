"""Tests for the defensive guards added to :mod:`antenati.iiif`.

These cover the manifest-shape failure modes that used to raise raw
``KeyError`` / ``IndexError`` exceptions and now surface as typed
:class:`antenati.errors.ManifestError`.
"""

from __future__ import annotations

import pytest

from antenati import iiif as antenati_iiif
from antenati.errors import ManifestError


def test_slice_canvases_missing_sequences_raises() -> None:
    with pytest.raises(ManifestError, match=r'sequences\[0\]\.canvases'):
        antenati_iiif.slice_canvases({}, 0, None)


def test_slice_canvases_empty_sequences_raises() -> None:
    with pytest.raises(ManifestError, match=r'sequences\[0\]\.canvases'):
        antenati_iiif.slice_canvases({'sequences': []}, 0, None)


def test_slice_canvases_missing_canvases_key_raises() -> None:
    with pytest.raises(ManifestError, match=r'sequences\[0\]\.canvases'):
        antenati_iiif.slice_canvases({'sequences': [{}]}, 0, None)


def test_slice_canvases_empty_canvases_raises() -> None:
    with pytest.raises(ManifestError, match='no canvases'):
        antenati_iiif.slice_canvases({'sequences': [{'canvases': []}]}, 0, None)


def test_image_url_for_canvas_missing_images_raises() -> None:
    with pytest.raises(ManifestError, match=r'images\[0\]\.resource'):
        antenati_iiif.image_url_for_canvas({})


def test_image_url_for_canvas_missing_resource_raises() -> None:
    with pytest.raises(ManifestError, match=r'images\[0\]\.resource'):
        antenati_iiif.image_url_for_canvas({'images': [{}]})


def test_image_url_for_canvas_missing_id_raises() -> None:
    with pytest.raises(ManifestError, match=r'images\[0\]\.resource'):
        antenati_iiif.image_url_for_canvas({'images': [{'resource': {}}]})


def test_image_url_for_canvas_happy_path() -> None:
    canvas = {'images': [{'resource': {'@id': 'https://example.org/x.jpg'}}]}
    assert antenati_iiif.image_url_for_canvas(canvas) == 'https://example.org/x.jpg'
