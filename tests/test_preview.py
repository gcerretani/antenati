from __future__ import annotations

from antenati.cli import _planned_filename
from antenati.downloader import DownloadItem


def test_preview_filename_comes_from_plan_without_http_metadata() -> None:
    item = DownloadItem(canvas={'label': 'Pag. 7'}, stem='pag-007', source_url='https://iiif.example.org/id/full/pct:100/0/default.jpg')
    assert _planned_filename(item) == 'pag-007.jpg'


def test_preview_normalizes_jpeg_extension() -> None:
    item = DownloadItem(canvas={}, stem='page', source_url='https://iiif.example.org/id/full/pct:100/0/default.jpeg')
    assert _planned_filename(item) == 'page.jpg'
