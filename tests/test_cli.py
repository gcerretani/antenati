from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from antenati import __version__
from antenati import cli as antenati_cli
from antenati.cli import app
from antenati.output import ExistingPolicy

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
    assert result.exit_code != 0
    assert 'No such option' not in result.output
    assert 'JSON output is scaffolded' in result.output


def test_no_url_fails_without_prompt_outside_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(antenati_cli, '_is_interactive_terminal', lambda: False)
    result = runner.invoke(app, [])
    assert result.exit_code != 0
    output = _ANSI_RE.sub('', result.output)
    assert 'URL is required outside an interactive terminal' in output


def test_interactive_wizard_builds_default_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeDownloader:
        def __init__(self, url: str, first: int, last: int | None, descriptive_names: bool = False):
            self.url = url
            self.first = first
            self.last = last
            self.descriptive_names = descriptive_names
            self.gallery_length = 15
            self.dirname = Path('generated-register')
            self.manifest = {'metadata': []}

        def load(self):
            return self

    answers = iter(
        [
            'https://antenati.cultura.gov.it/ark:/12657/an_ua19944535/test',
            'all',
            'full',
            str(tmp_path / 'download'),
        ]
    )
    monkeypatch.setattr(antenati_cli, '_is_interactive_terminal', lambda: True)
    monkeypatch.setattr(antenati_cli, 'Downloader', FakeDownloader)
    monkeypatch.setattr(antenati_cli.typer, 'prompt', lambda *_args, **_kwargs: next(answers))
    monkeypatch.setattr(antenati_cli.typer, 'confirm', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(antenati_cli.cli_ui, 'render_banner', lambda: None)
    monkeypatch.setattr(antenati_cli.cli_ui, 'render_register', lambda *_args, **_kwargs: None)

    config, downloader = antenati_cli._run_wizard(show_status=False)

    assert config.url.endswith('/test')
    assert config.first == 0
    assert config.last is None
    assert config.size == 0
    assert config.output_dir == str(tmp_path / 'download')
    assert downloader is not None
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
    assert 'locked destination' in result.output
    assert 'Traceback' not in result.output


def test_debug_logging_keeps_third_party_http_quiet() -> None:
    antenati_logger = logging.getLogger('antenati')
    urllib3_logger = logging.getLogger('urllib3')
    old_antenati_level = antenati_logger.level
    old_urllib3_level = urllib3_logger.level
    try:
        antenati_cli._configure_logging(verbosity=0, debug=True)
        assert antenati_logger.level == logging.DEBUG
        assert urllib3_logger.level == logging.WARNING
    finally:
        antenati_logger.setLevel(old_antenati_level)
        urllib3_logger.setLevel(old_urllib3_level)


def test_run_cli_without_progress_does_not_create_rich_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()

    def fail_progress(*_args, **_kwargs):
        pytest.fail('Rich progress should not be created when show_progress=False')

    def fake_run_with_policy(_downloader, *, n_workers, size, progress, policy):
        assert n_workers == 2
        assert size == 0
        assert policy is ExistingPolicy.OVERWRITE
        progress.set_total(15)
        progress.update()
        return sentinel

    monkeypatch.setattr(antenati_cli, 'Progress', fail_progress)
    monkeypatch.setattr(antenati_cli, 'run_with_policy', fake_run_with_policy)

    result = antenati_cli.run_cli(object(), n_workers=2, size=0, show_progress=False)

    assert result is sentinel


def test_run_cli_starts_progress_only_after_total_is_known(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[object] = []
    sentinel = object()

    class FakeProgress:
        def __init__(self, *_args, **_kwargs):
            events.append('init')

        def start(self) -> None:
            events.append('start')

        def add_task(self, _description: str, *, total: int):
            events.append(('add', total))
            return 1

        def update(self, _task_id: int, *, total: int) -> None:
            events.append(('set-total', total))

        def advance(self, _task_id: int) -> None:
            events.append('advance')

        def stop(self) -> None:
            events.append('stop')

    def fake_run_with_policy(_downloader, *, n_workers, size, progress, policy):
        assert events == ['init']
        progress.set_total(15)
        progress.update()
        return sentinel

    monkeypatch.setattr(antenati_cli, 'Progress', FakeProgress)
    monkeypatch.setattr(antenati_cli, 'run_with_policy', fake_run_with_policy)

    result = antenati_cli.run_cli(object(), n_workers=2, size=0)

    assert result is sentinel
    assert events == ['init', 'start', ('add', 15), 'advance', 'stop']
