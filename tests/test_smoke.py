"""Smoke tests: verify the module can be imported and exposes its public API.

This is the seed of the offline test suite. As the refactor extracts pure
modules (iiif, http, paths, downloader, ...), per-module unit tests will be
added next to this file. Live-download tests live under tests/integration/
behind the `integration` marker.
"""

import sys
import warnings

import pytest

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


def test_gui_version_flag_prints_version_without_creating_a_window(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    pytest.importorskip('tkinter')
    import antenati.gui
    import antenati.gui.app as gui_app

    def _fail_if_called() -> None:
        raise AssertionError('the --version flag must not start the Tk event loop')

    monkeypatch.setattr(gui_app, 'main', _fail_if_called)
    monkeypatch.setattr(sys, 'argv', ['antenati_gui', '--version'])

    antenati.gui.main()

    assert capsys.readouterr().out.strip() == antenati.__version__
