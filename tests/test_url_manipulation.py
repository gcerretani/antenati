"""Tests for ``manipulate_image_url``: the IIIF size rewriter."""

from __future__ import annotations

import pytest

import antenati_iiif

ORIGINAL = 'https://iiif.example.org/iiif/img1/full/full/0/default.jpg'


def test_size_zero_uses_pct_100() -> None:
    rewritten = antenati_iiif.manipulate_image_url(ORIGINAL, 0)
    assert rewritten == 'https://iiif.example.org/iiif/img1/full/pct:100/0/default.jpg'


@pytest.mark.parametrize('size', [200, 1000, 5000])
def test_positive_size_uses_constrained_box(size: int) -> None:
    rewritten = antenati_iiif.manipulate_image_url(ORIGINAL, size)
    assert f'/full/!{size},{size}/0/' in rewritten
    assert '/full/full/0/' not in rewritten


def test_url_without_full_full_is_returned_unchanged() -> None:
    weird = 'https://iiif.example.org/iiif/img1/info.json'
    assert antenati_iiif.manipulate_image_url(weird, 0) == weird


def test_image_url_for_canvas_extracts_resource_id(manifest_dict: dict) -> None:
    canvas = manifest_dict['sequences'][0]['canvases'][0]
    assert antenati_iiif.image_url_for_canvas(canvas).endswith('/img1/full/full/0/default.jpg')
