from __future__ import annotations

import pytest
import responses

from antenati import Downloader, ProgressBar
from antenati.errors import ValidationError
from antenati.gui.worker import DownloadParams
from antenati.validation import DownloadOptions


def _null_progress() -> ProgressBar:
    return ProgressBar(set_total=lambda _t: None, update=lambda: None)


@pytest.mark.parametrize(
    'options',
    [
        DownloadOptions(first=-1),
        DownloadOptions(first=2, last=2),
        DownloadOptions(first=3, last=2),
        DownloadOptions(size=-1),
        DownloadOptions(n_workers=0),
        DownloadOptions(n_workers=65),
    ],
)
def test_shared_options_reject_invalid_values(options: DownloadOptions) -> None:
    with pytest.raises(ValidationError):
        options.validate()


def test_programmatic_run_rejects_invalid_workers_before_network() -> None:
    downloader = Downloader('https://antenati.cultura.gov.it/ark:/12657/an_ua1/gallery', 0, None)
    with responses.RequestsMock() as mocked:
        with pytest.raises(ValidationError, match='n_workers'):
            downloader.run(n_workers=0, size=0, progress=_null_progress())
        assert len(mocked.calls) == 0


def test_gui_params_use_same_core_validation() -> None:
    params = DownloadParams(url='https://example.invalid/manifest', output_dir='.', size=-1, first=0, last=None)
    with pytest.raises(ValidationError, match='size'):
        params.validate(require_output=True)
