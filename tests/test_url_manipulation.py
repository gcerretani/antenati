"""Tests for ``__manipulate_url``: the IIIF size rewriter."""

from __future__ import annotations

import pytest

from antenati import AntenatiDownloader

_manipulate_url = (
    AntenatiDownloader._AntenatiDownloader__manipulate_url  # type: ignore[attr-defined]
)

ORIGINAL = 'https://iiif.example.org/iiif/img1/full/full/0/default.jpg'


def test_size_zero_uses_pct_100() -> None:
    rewritten = _manipulate_url(ORIGINAL, 0)
    assert rewritten == 'https://iiif.example.org/iiif/img1/full/pct:100/0/default.jpg'


@pytest.mark.parametrize('size', [200, 1000, 5000])
def test_positive_size_uses_constrained_box(size: int) -> None:
    rewritten = _manipulate_url(ORIGINAL, size)
    assert f'/full/!{size},{size}/0/' in rewritten
    assert '/full/full/0/' not in rewritten


def test_url_without_full_full_is_returned_unchanged() -> None:
    weird = 'https://iiif.example.org/iiif/img1/info.json'
    assert _manipulate_url(weird, 0) == weird
