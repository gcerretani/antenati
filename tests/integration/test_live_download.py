"""Live integration tests against the real Portale Antenati.

These tests are slow, hit a third-party server, and may flake when the
Antenati SAN reverse proxy is overloaded or under WAF challenge. They
are gated by the ``integration`` pytest marker and excluded from CI's
default ``pytest -m "not integration"`` runs; the daily ``live.yml``
workflow runs them on schedule so we hear early if the gallery shape
changes.

To run locally::

    pytest -m integration
"""

from __future__ import annotations

from pathlib import Path

import pytest

from antenati.downloader import Downloader, ProgressBar

# A small, stable gallery used as the canary. The same URL has been the
# project's smoke target since v2.5.
LIVE_URL = 'https://antenati.cultura.gov.it/ark:/12657/an_ua19944535/w9DWR8x'


def _null_progress() -> ProgressBar:
    return ProgressBar(set_total=lambda _t: None, update=lambda: None)


@pytest.mark.integration
def test_download_two_canvases_succeeds(tmp_path: Path) -> None:
    # Download only the first two canvases to keep the test under a few
    # seconds of wall time and well within the SAN server's rate limits.
    downloader = Downloader(LIVE_URL, first=0, last=2)
    downloader.check_dir(parentdir=str(tmp_path), interactive=False)
    total = downloader.run(n_workers=2, size=200, progress=_null_progress())

    files = sorted(downloader.dirname.iterdir())
    assert len(files) == 2, f'expected 2 files, got {[f.name for f in files]}'
    assert total > 0
