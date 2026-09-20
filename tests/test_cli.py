from __future__ import annotations

from typer.testing import CliRunner

from antenati import __version__
from antenati.cli import app

runner = CliRunner()


def test_cli_help_uses_modern_workers_name_and_keeps_legacy_alias() -> None:
    result = runner.invoke(app, ['--help'])
    assert result.exit_code == 0
    assert '--workers' in result.output
    assert '--nthreads' in result.output
    assert '-n' in result.output
    assert '--format' in result.output


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
