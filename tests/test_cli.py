from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from antenati import __version__
from antenati import cli as antenati_cli
from antenati.cli import app

runner = CliRunner()
_ANSI_RE = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


def test_cli_help_uses_modern_workers_name_and_keeps_legacy_alias() -> None:
    result = runner.invoke(app, ['--help'])
    assert result.exit_code == 0
    output = _ANSI_RE.sub('', result.output)
    assert '--workers' in output
    assert '--nthreads' in output
    assert '-n' in output
    assert '--format' in output


def test_cli_version_short_alias_still_works() -> None:
    result = runner.invoke(app, ['-v'])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_cli_version_long_alias_still_works() -> None:
    result = runner.invoke(app, ['--version'])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_legacy_flags_are_accepted_by_typer_parser() -> None:
    result = runner.invoke(
        app,
        [
            'https://antenati.cultura.gov.it/ark:/12657/an_ua19944535/test',
            '-s',
            '2000',
            '-n',
            '4',
            '--nthreads',
            '4',
            '-f',
            '1',
            '-l',
            '2',
            '-d',
            '-o',
            'out',
            '--existing',
            'resume',
            '--dry-run',
            '--format',
            'json',
        ],
    )
    # JSON rendering is deliberately not implemented in this preliminary PR.
    # Reaching that error proves Typer accepted the legacy and modern spellings.
    assert result.exit_code != 0
    assert 'No such option' not in result.output
    assert 'JSON output is scaffolded' in result.output


def test_no_url_fails_without_prompt_outside_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(antenati_cli, '_is_interactive_terminal', lambda: False)
    result = runner.invoke(app, [])
    assert result.exit_code != 0
    assert 'Missing argument URL' in result.output


def test_interactive_wizard_builds_default_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeDownloader:
        def __init__(self, url: str, first: int, last: int | None, descriptive_names: bool = False):
            self.url = url
            self.first = first
            self.last = last
            self.descriptive_names = descriptive_names
            self.gallery_length = 15
            self.dirname = Path('generated-register')

        def load(self):
            return self

        def print_gallery_info(self) -> None:
            return None

    answers = iter([
        'https://antenati.cultura.gov.it/ark:/12657/an_ua19944535/test',
        'all',
        'full',
        str(tmp_path / 'download'),
    ])
    monkeypatch.setattr(antenati_cli, '_is_interactive_terminal', lambda: True)
    monkeypatch.setattr(antenati_cli, 'Downloader', FakeDownloader)
    monkeypatch.setattr(antenati_cli.typer, 'prompt', lambda *_args, **_kwargs: next(answers))
    monkeypatch.setattr(antenati_cli.typer, 'confirm', lambda *_args, **_kwargs: True)

    config, downloader = antenati_cli._run_wizard()

    assert config.url.endswith('/test')
    assert config.first == 0
    assert config.last is None
    assert config.size == 0
    assert config.output_dir == str(tmp_path / 'download')
    assert downloader.url == config.url


def test_operational_error_is_concise_without_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingDownloader:
        def __init__(self, *_args, **_kwargs):
            pass

        def load(self):
            raise PermissionError('locked destination')

    monkeypatch.setattr(antenati_cli, 'Downloader', FailingDownloader)
    result = runner.invoke(app, ['https://antenati.cultura.gov.it/ark:/12657/an_ua19944535/test'])

    assert result.exit_code == 1
    assert 'Error: locked destination' in result.output
    assert 'Traceback' not in result.output
