from __future__ import annotations

import pytest

from antenati.config import DownloadConfig
from antenati.errors import ValidationError
from antenati.output import ExistingPolicy


def test_shared_config_carries_cli_gui_core_options() -> None:
    config = DownloadConfig(
        url='https://example.invalid/manifest',
        output_dir='archive',
        size=800,
        first=2,
        last=5,
        n_workers=4,
        descriptive_names=True,
        existing_policy=ExistingPolicy.RESUME,
    ).validate(require_output=True)
    assert config.options().n_workers == 4
    assert config.descriptive_names
    assert config.existing_policy is ExistingPolicy.RESUME


def test_shared_config_requires_output_for_gui_execution() -> None:
    config = DownloadConfig(url='https://example.invalid/manifest')
    with pytest.raises(ValidationError, match='output directory'):
        config.validate(require_output=True)
