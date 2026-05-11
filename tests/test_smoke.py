"""Smoke tests: verify the module can be imported and exposes its public API.

This is the seed of the offline test suite. As the refactor extracts pure
modules (iiif, http, paths, downloader, ...), per-module unit tests will be
added next to this file. Live-download tests live under tests/integration/
behind the `integration` marker.
"""

import warnings

import antenati


def test_module_imports() -> None:
    assert antenati.__version__
    assert antenati.Downloader is not None
    assert antenati.ProgressBar is not None
    assert antenati.DEFAULT_SIZE == 0
    assert antenati.DEFAULT_N_THREADS == 2


def test_antentati_downloader_alias_emits_deprecation_warning() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        cls = antenati.AntenatiDownloader
    assert cls is antenati.Downloader
    assert len(caught) == 1
    w = caught[0]
    assert issubclass(w.category, DeprecationWarning)
    assert 'AntenatiDownloader' in str(w.message)
    assert 'v7.0' in str(w.message)
