"""Smoke tests: verify the module can be imported and exposes its public API.

This is the seed of the offline test suite. As the refactor extracts pure
modules (iiif, http, paths, downloader, ...), per-module unit tests will be
added next to this file. Live-download tests live under tests/integration/
behind the `integration` marker.
"""

import antenati


def test_module_imports() -> None:
    assert antenati.__version__
    assert antenati.AntenatiDownloader is not None
    assert antenati.ProgressBar is not None
    assert antenati.DEFAULT_SIZE == 0
    assert antenati.DEFAULT_N_THREADS == 2
