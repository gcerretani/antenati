"""Tests for metadata extraction and directory name generation."""

from __future__ import annotations

import pytest

from antenati import Downloader
from antenati import iiif as antenati_iiif
from antenati.errors import ManifestError


def test_get_metadata_value_finds_label(manifest_dict: dict) -> None:
    assert antenati_iiif.get_metadata_value(manifest_dict, 'Titolo') == '1900'
    assert antenati_iiif.get_metadata_value(manifest_dict, 'Tipologia') == 'Nati'


def test_get_metadata_value_unknown_label_raises(manifest_dict: dict) -> None:
    with pytest.raises(ManifestError, match='Cannot get'):
        antenati_iiif.get_metadata_value(manifest_dict, 'does-not-exist')


def test_get_metadata_value_without_metadata_field_raises() -> None:
    with pytest.raises(ManifestError, match="no 'metadata' field"):
        antenati_iiif.get_metadata_value({}, 'Titolo')


def test_generate_dirname_combines_metadata_and_archive_id(
    downloader: Downloader,
) -> None:
    # slugify lowercases and replaces slashes/spaces with single dashes
    name = str(downloader.dirname)
    assert '1900' in name
    assert 'nati' in name
    assert downloader.archive_id in name
    assert 'stato-civile-italiano' in name


def test_print_gallery_info_outputs_metadata(downloader: Downloader, capsys: pytest.CaptureFixture[str]) -> None:
    downloader.print_gallery_info()
    out = capsys.readouterr().out
    assert 'Contesto archivistico' in out
    assert 'Tipologia' in out
    assert '3 images found.' in out
