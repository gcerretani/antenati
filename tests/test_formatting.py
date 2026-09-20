from __future__ import annotations

from antenati.formatting import plain_text


def test_plain_text_strips_metadata_html_and_decodes_entities() -> None:
    value = '<a href="https://example.test/path">https://example.test/path</a> &amp; other'
    assert plain_text(value) == 'https://example.test/path & other'


def test_plain_text_collapses_whitespace() -> None:
    assert plain_text('  Archivio   di\n Stato ') == 'Archivio di Stato'
