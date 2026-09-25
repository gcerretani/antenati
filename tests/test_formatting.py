from __future__ import annotations

from antenati.formatting import metadata_rows, plain_text


def test_plain_text_strips_metadata_html_and_decodes_entities() -> None:
    value = '<a href="https://example.test/path">https://example.test/path</a> &amp; other'
    assert plain_text(value) == 'https://example.test/path & other'


def test_plain_text_collapses_whitespace() -> None:
    assert plain_text('  Archivio   di\n Stato ') == 'Archivio di Stato'


def test_metadata_rows_cleans_values_and_skips_empty_or_malformed_entries() -> None:
    manifest = {
        'metadata': [
            {'label': 'Tipologia', 'value': '<b>Matrimoni</b>'},
            {'label': '', 'value': ''},
            'not-a-dict',
            {'label': 'Vedi il registro', 'value': '<a href="https://example.test/r">https://example.test/r</a>'},
        ]
    }
    assert metadata_rows(manifest) == [('Tipologia', 'Matrimoni'), ('Vedi il registro', 'https://example.test/r')]
    assert metadata_rows({}) == []
