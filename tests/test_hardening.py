"""Regression tests for correctness and hardening fixes introduced in v6.2."""

from __future__ import annotations

import threading
from pathlib import Path

from antenati import Downloader, ProgressBar, iiif


def _null_progress() -> ProgressBar:
    return ProgressBar(set_total=lambda _t: None, update=lambda: None)


def test_duplicate_canvas_labels_receive_unique_stems(downloader: Downloader) -> None:
    downloader.canvases[1]['label'] = downloader.canvases[0]['label']
    stems = downloader._Downloader__build_unique_stems()  # noqa: SLF001 - regression test of planning invariant
    assert len(stems) == len(set(stems))
    assert stems[0] == '0001'
    assert stems[1] == '0001-2'


def test_preset_cancel_performs_no_additional_http_requests(mocked_http, downloader: Downloader, tmp_path: Path) -> None:
    downloader.check_dir(parentdir=str(tmp_path), interactive=False)
    requests_before_run = len(mocked_http.calls)
    cancel = threading.Event()
    cancel.set()

    assert downloader.run(n_workers=2, size=0, progress=_null_progress(), cancel=cancel) == 0
    assert len(mocked_http.calls) == requests_before_run
    assert list(downloader.dirname.iterdir()) == []


def test_archive_id_is_not_confused_by_explicit_https_port() -> None:
    url = 'https://antenati.cultura.gov.it:8443/ark:/12657/an_ua19944535/example'
    assert iiif.get_archive_id_from_url(url) == '19944535'


def test_manifest_parser_binds_url_to_manifest_id() -> None:
    html = '''
    <script>
      const unrelated = "https://example.invalid/not-the-manifest";
      const manifestId = "https://iiif.example.org/archive/manifest";
    </script>
    '''
    assert iiif.parse_manifest_url_from_html(html, 'https://antenati.example/gallery') == 'https://iiif.example.org/archive/manifest'


def test_image_size_rewrite_handles_max_source_form() -> None:
    url = 'https://iiif.example.org/iiif/2/img1/full/max/0/default.jpg'
    assert iiif.manipulate_image_url(url, 1200) == 'https://iiif.example.org/iiif/2/img1/full/!1200,1200/0/default.jpg'
