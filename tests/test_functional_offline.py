"""Offline functional tests using a real local HTTP server.

Unlike the ``responses``-based tests, these cases exercise the actual Requests
socket/streaming path, filesystem writes and selected CLI flows without
contacting the Portale Antenati.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from antenati import Downloader, ProgressBar
from antenati.output import ExistingPolicy, prepare_output, run_with_policy
from tests.conftest import TINY_JPEG


@dataclass
class _ServerState:
    base_url: str = ''
    pages: int = 15
    requests: Counter[str] = field(default_factory=Counter)
    corrupt_pages: set[int] = field(default_factory=set)

    @property
    def manifest_url(self) -> str:
        return f'{self.base_url}/manifest'

    @property
    def gallery_url(self) -> str:
        return f'{self.base_url}/ark:/12657/an_ua19944535/gallery'

    def manifest(self) -> dict:
        canvases = []
        for page in range(1, self.pages + 1):
            canvases.append(
                {
                    '@id': f'{self.base_url}/ark:/12657/an_ua19944535/canvas/p{page}',
                    '@type': 'sc:Canvas',
                    'label': f'Pag. {page}',
                    'images': [
                        {
                            '@type': 'oa:Annotation',
                            'resource': {
                                '@id': f'{self.base_url}/iiif/img{page}/full/max/0/default.jpg',
                                '@type': 'dctypes:Image',
                                'format': 'image/jpeg',
                            },
                        }
                    ],
                }
            )
        return {
            '@context': 'http://iiif.io/api/presentation/2/context.json',
            '@id': self.manifest_url,
            '@type': 'sc:Manifest',
            'label': 'Offline functional gallery',
            'metadata': [
                {'label': 'Contesto archivistico', 'value': 'Functional tests/Comune di Esempio'},
                {'label': 'Titolo', 'value': '1900'},
                {'label': 'Tipologia', 'value': 'Nati'},
            ],
            'sequences': [{'@type': 'sc:Sequence', 'canvases': canvases}],
        }

    @property
    def image_requests(self) -> int:
        return sum(count for path, count in self.requests.items() if path.startswith('/iiif/'))

    def reset_requests(self) -> None:
        self.requests.clear()


class _Handler(BaseHTTPRequestHandler):
    server: _FunctionalServer

    def do_GET(self) -> None:
        state = self.server.state
        state.requests[self.path] += 1
        if self.path == '/manifest':
            self._send('application/json; charset=utf-8', json.dumps(state.manifest()).encode())
            return
        if self.path == '/ark:/12657/an_ua19944535/gallery':
            body = f'<script>const manifestId = "{state.manifest_url}";</script>'.encode()
            self._send('text/html; charset=utf-8', body)
            return
        if self.path.startswith('/iiif/img') and self.path.endswith('/0/default.jpg'):
            page = int(self.path.split('/')[2].removeprefix('img'))
            payload = b'not-a-jpeg' if page in state.corrupt_pages else TINY_JPEG
            self._send('image/jpeg', payload)
            return
        self.send_error(404)

    def _send(self, content_type: str, body: bytes) -> None:
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


class _FunctionalServer(ThreadingHTTPServer):
    state: _ServerState


@contextmanager
def _fake_iiif_server() -> Iterator[_ServerState]:
    state = _ServerState()
    server = _FunctionalServer(('127.0.0.1', 0), _Handler)
    state.base_url = f'http://127.0.0.1:{server.server_port}'
    server.state = state
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _progress() -> ProgressBar:
    return ProgressBar(set_total=lambda _total: None, update=lambda: None)


def _run(state: _ServerState, output: Path, *, size: int = 0, policy: ExistingPolicy = ExistingPolicy.OVERWRITE):
    downloader = Downloader(state.manifest_url, first=0, last=None)
    downloader.load()
    prepare_output(downloader, output, policy)
    return run_with_policy(downloader, n_workers=3, size=size, progress=_progress(), policy=policy)


def _image_names(output: Path) -> list[str]:
    return sorted(path.name for path in output.glob('*.jpg'))


def _cli(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, '-m', 'antenati.cli', *args],
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def test_real_http_full_download_writes_images_and_provenance(tmp_path: Path) -> None:
    with _fake_iiif_server() as state:
        output = tmp_path / 'archive'
        report = _run(state, output)

        assert report.successful
        assert report.expected == report.completed == 15
        assert state.image_requests == 15
        assert _image_names(output) == [f'pag-{page:02d}.jpg' for page in range(1, 16)]
        assert (output / '.antenati-manifest.json').is_file()
        index = json.loads((output / '.antenati-index.json').read_text(encoding='utf-8'))
        assert len(index['images']) == 15


def test_real_http_gallery_html_to_manifest_to_images(tmp_path: Path) -> None:
    with _fake_iiif_server() as state:
        output = tmp_path / 'archive'
        downloader = Downloader(state.gallery_url, first=0, last=2)
        downloader.load()
        prepare_output(downloader, output, ExistingPolicy.OVERWRITE)
        report = run_with_policy(downloader, n_workers=2, size=0, progress=_progress(), policy=ExistingPolicy.OVERWRITE)

        assert report.successful
        assert _image_names(output) == ['pag-01.jpg', 'pag-02.jpg']
        assert state.requests['/ark:/12657/an_ua19944535/gallery'] == 1
        assert state.requests['/manifest'] == 1
        assert state.image_requests == 2


def test_real_http_resume_makes_no_image_requests_when_everything_is_valid(tmp_path: Path) -> None:
    with _fake_iiif_server() as state:
        output = tmp_path / 'archive'
        _run(state, output)
        state.reset_requests()

        report = _run(state, output, policy=ExistingPolicy.RESUME)

        assert report.successful
        assert report.completed == 0
        assert report.skipped == 15
        assert state.image_requests == 0


def test_real_http_resume_redownloads_only_missing_file(tmp_path: Path) -> None:
    with _fake_iiif_server() as state:
        output = tmp_path / 'archive'
        _run(state, output)
        (output / 'pag-07.jpg').unlink()
        state.reset_requests()

        report = _run(state, output, policy=ExistingPolicy.RESUME)

        assert report.successful
        assert report.completed == 1
        assert report.skipped == 14
        assert state.image_requests == 1
        assert (output / 'pag-07.jpg').read_bytes() == TINY_JPEG


def test_real_http_resume_redownloads_only_hash_mismatched_file(tmp_path: Path) -> None:
    with _fake_iiif_server() as state:
        output = tmp_path / 'archive'
        _run(state, output)
        (output / 'pag-08.jpg').write_bytes(b'corrupt-local-file')
        state.reset_requests()

        report = _run(state, output, policy=ExistingPolicy.RESUME)

        assert report.successful
        assert report.completed == 1
        assert report.skipped == 14
        assert state.image_requests == 1
        assert (output / 'pag-08.jpg').read_bytes() == TINY_JPEG


def test_real_http_resume_redownloads_all_when_requested_size_changes(tmp_path: Path) -> None:
    with _fake_iiif_server() as state:
        output = tmp_path / 'archive'
        _run(state, output, size=0)
        state.reset_requests()

        report = _run(state, output, size=200, policy=ExistingPolicy.RESUME)

        assert report.successful
        assert report.completed == 15
        assert report.skipped == 0
        assert state.image_requests == 15
        assert any('/!200,200/' in path for path in state.requests)


def test_real_http_corrupt_remote_image_is_not_committed(tmp_path: Path) -> None:
    with _fake_iiif_server() as state:
        state.corrupt_pages.add(4)
        output = tmp_path / 'archive'
        report = _run(state, output)

        assert not report.successful
        assert report.completed == 14
        assert len(report.failed) == 1
        assert not (output / 'pag-04.jpg').exists()
        assert not list(output.glob('*.tmp'))


def test_cli_dry_run_uses_real_http_but_downloads_no_images(tmp_path: Path) -> None:
    with _fake_iiif_server() as state:
        output = tmp_path / 'archive'
        result = _cli(state.manifest_url, '--output', str(output), '--dry-run')

        assert result.returncode == 0, result.stderr
        assert 'pag-01.jpg' in result.stdout
        assert 'pag-15.jpg' in result.stdout
        assert state.image_requests == 0
        assert not output.exists()


def test_cli_default_ask_can_resume_existing_real_download(tmp_path: Path) -> None:
    with _fake_iiif_server() as state:
        output = tmp_path / 'archive'
        first = _cli(state.manifest_url, '--output', str(output), '--existing', 'overwrite')
        assert first.returncode == 0, first.stderr
        state.reset_requests()

        resumed = _cli(state.manifest_url, '--output', str(output), input_text='resume\n')

        assert resumed.returncode == 0, resumed.stderr
        assert 'Choose how to handle existing files' in resumed.stdout
        assert 'skipped: 15' in resumed.stdout
        assert state.image_requests == 0


def test_cli_explicit_error_policy_fails_cleanly_on_existing_output(tmp_path: Path) -> None:
    with _fake_iiif_server() as state:
        output = tmp_path / 'archive'
        first = _cli(state.manifest_url, '--output', str(output), '--existing', 'overwrite')
        assert first.returncode == 0, first.stderr
        state.reset_requests()

        second = _cli(state.manifest_url, '--output', str(output), '--existing', 'error')

        assert second.returncode != 0
        assert 'already exists and is not empty' in second.stderr
        assert state.image_requests == 0
