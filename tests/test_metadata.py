"""Tests for metadata extraction and directory name generation."""

from __future__ import annotations

import pytest

from antenati import AntenatiDownloader

# Name-mangled private accessor — see test_iiif_parsing.py for context.
_get_metadata_content = (
    AntenatiDownloader._AntenatiDownloader__get_metadata_content  # type: ignore[attr-defined]
)


def test_metadata_lookup_by_label(downloader: AntenatiDownloader) -> None:
    assert _get_metadata_content(downloader, 'Titolo') == '1900'
    assert _get_metadata_content(downloader, 'Tipologia') == 'Nati'


def test_metadata_lookup_unknown_label_raises(downloader: AntenatiDownloader) -> None:
    with pytest.raises(RuntimeError, match='Cannot get'):
        _get_metadata_content(downloader, 'does-not-exist')


def test_generate_dirname_combines_metadata_and_archive_id(
    downloader: AntenatiDownloader,
) -> None:
    # slugify lowercases and replaces slashes/spaces with single dashes
    name = str(downloader.dirname)
    assert '1900' in name
    assert 'nati' in name
    assert downloader.archive_id in name
    assert 'stato-civile-italiano' in name


def test_print_gallery_info_outputs_metadata(downloader: AntenatiDownloader, capsys: pytest.CaptureFixture[str]) -> None:
    downloader.print_gallery_info()
    out = capsys.readouterr().out
    assert 'Contesto archivistico' in out
    assert 'Tipologia' in out
    assert '3 images found.' in out
