from __future__ import annotations

import pytest

from antenati.downloader import Downloader


def _canvases(count: int) -> list[dict[str, object]]:
    return [{'label': f'Pag. {index}'} for index in range(1, count + 1)]


@pytest.mark.parametrize(
    ('count', 'first', 'last'),
    [
        (9, 'pag-1', 'pag-9'),
        (15, 'pag-01', 'pag-15'),
        (150, 'pag-001', 'pag-150'),
        (1200, 'pag-0001', 'pag-1200'),
    ],
)
def test_numeric_labels_are_padded_to_gallery_width(count: int, first: str, last: str) -> None:
    downloader = Downloader('https://example.invalid/manifest', 0, None)
    stems = downloader._build_unique_stems(_canvases(count))
    assert stems[0] == first
    assert stems[-1] == last
    assert stems == sorted(stems)


def test_partial_range_reuses_full_gallery_stems() -> None:
    downloader = Downloader('https://example.invalid/manifest', 6, 12)
    stems = downloader._build_unique_stems(_canvases(150))
    assert stems[6:12] == ['pag-007', 'pag-008', 'pag-009', 'pag-010', 'pag-011', 'pag-012']


def test_non_numeric_labels_are_preserved_and_collisions_stay_deterministic() -> None:
    downloader = Downloader('https://example.invalid/manifest', 0, None)
    canvases = [{'label': 'Frontespizio'}, {'label': 'Frontespizio'}, {'label': ''}]
    assert downloader._build_unique_stems(canvases) == ['frontespizio', 'frontespizio-2', 'image-3']
