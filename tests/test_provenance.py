from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import responses

from antenati import Downloader, ProgressBar
from antenati.provenance import INDEX_FILENAME, MANIFEST_FILENAME
from tests.conftest import GALLERY_URL, TINY_JPEG


def _null_progress() -> ProgressBar:
    return ProgressBar(set_total=lambda _t: None, update=lambda: None)


def test_run_persists_manifest_and_per_image_provenance(mocked_http, tmp_path: Path) -> None:
    downloader = Downloader(GALLERY_URL, first=0, last=1)
    downloader.check_dir(parentdir=str(tmp_path), interactive=False)
    image_url = 'https://iiif.example.org/iiif/img1/full/pct:100/0/default.jpg'
    mocked_http.add(responses.GET, image_url, body=TINY_JPEG, status=200, content_type='image/jpeg')

    report = downloader.run(n_workers=1, size=0, progress=_null_progress())
    assert report.successful

    manifest_path = downloader.dirname / MANIFEST_FILENAME
    index_path = downloader.dirname / INDEX_FILENAME
    assert manifest_path.is_file()
    assert index_path.is_file()

    index = json.loads(index_path.read_text(encoding='utf-8'))
    assert index['source_url'] == GALLERY_URL
    assert index['requested_size'] == 0
    assert len(index['images']) == 1
    record = index['images'][0]
    assert record['canvas_id'].endswith('/iiif-19944535/canvas/1')
    assert record['source_url'] == image_url
    assert record['filename'] == '0001.jpg'
    assert record['byte_size'] == len(TINY_JPEG)
    assert record['sha256'] == sha256(TINY_JPEG).hexdigest()
