"""Interface localisation: locale detection and catalog consistency."""

from __future__ import annotations

import string

import pytest

from antenati import i18n

_LOCALE_VARS = ('ANTENATI_LANG', 'LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG')


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for var in _LOCALE_VARS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        ('it_IT.UTF-8', 'it'),
        ('fr_CA', 'fr'),
        ('es-ES', 'es'),
        ('en_GB.UTF-8', 'en'),
        ('Italian_Italy', 'it'),
        ('de_DE.UTF-8', None),
        ('C', None),
        ('', None),
    ],
)
def test_normalize(value: str, expected: str | None) -> None:
    assert i18n._normalize(value) == expected


def test_override_wins(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv('LANG', 'fr_FR.UTF-8')
    clean_env.setenv('ANTENATI_LANG', 'es')
    assert i18n.detect_language() == 'es'


def test_posix_env(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv('LANG', 'it_IT.UTF-8')
    assert i18n.detect_language() == 'it'


def test_language_list_picks_first_supported(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv('LANGUAGE', 'de:fr:it')
    assert i18n.detect_language() == 'fr'


def test_unsupported_locale_falls_back_to_english(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv('LC_ALL', 'de_DE.UTF-8')
    assert i18n.detect_language() == 'en'


def test_translation_and_formatting() -> None:
    i18n.set_language('it')
    assert i18n._('Support this project') == 'Sostieni il progetto'
    assert i18n._('{count} pages', count=3) == '3 pagine'
    assert i18n._('untranslated message') == 'untranslated message'
    i18n.set_language('en')
    assert i18n._('{count} pages', count=3) == '3 pages'


def _fields(text: str) -> set[str]:
    return {name for _literal, name, _spec, _conv in string.Formatter().parse(text) if name}


def test_catalogs_share_keys_and_placeholders() -> None:
    keys = set(i18n.CATALOGS['it'])
    for lang, catalog in i18n.CATALOGS.items():
        assert set(catalog) == keys, lang
        for source, translated in catalog.items():
            assert _fields(source) == _fields(translated), (lang, source)
