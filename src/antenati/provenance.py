# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistent provenance metadata for downloaded Antenati galleries."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

MANIFEST_FILENAME = '.antenati-manifest.json'
INDEX_FILENAME = '.antenati-index.json'
INDEX_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ImageRecord:
    """Persistent mapping from one local file to its IIIF source."""

    canvas_id: str
    label: str
    source_url: str
    filename: str
    requested_size: int
    byte_size: int
    sha256: str
    downloaded_at: str

    @classmethod
    def create(
        cls,
        *,
        canvas_id: str,
        label: str,
        source_url: str,
        filename: str,
        requested_size: int,
        byte_size: int,
        sha256: str,
    ) -> ImageRecord:
        return cls(
            canvas_id=canvas_id,
            label=label,
            source_url=source_url,
            filename=filename,
            requested_size=requested_size,
            byte_size=byte_size,
            sha256=sha256,
            downloaded_at=datetime.now(timezone.utc).isoformat(),
        )


def _atomic_write_text(path: Path, text: str) -> None:
    """Replace a metadata file atomically in its destination directory."""
    temp_name: str | None = None
    try:
        with NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp', delete=False) as tmp:
            temp_name = tmp.name
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


def write_provenance(
    directory: Path,
    *,
    source_url: str,
    manifest_url: str,
    manifest: dict[str, Any],
    archive_id: str,
    ark_id: str,
    requested_size: int,
    records: list[ImageRecord],
) -> None:
    """Persist the normalized manifest and a per-image provenance index."""
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    _atomic_write_text(directory / MANIFEST_FILENAME, manifest_text)

    payload = {
        'schema_version': INDEX_SCHEMA_VERSION,
        'source_url': source_url,
        'manifest_url': manifest_url,
        'archive_id': archive_id,
        'ark_id': ark_id,
        'requested_size': requested_size,
        'images': [asdict(record) for record in records],
    }
    index_text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    _atomic_write_text(directory / INDEX_FILENAME, index_text)


def read_index(directory: Path) -> dict[str, Any] | None:
    """Return a previously persisted index, or ``None`` when absent."""
    path = directory / INDEX_FILENAME
    if not path.exists():
        return None
    with path.open(encoding='utf-8') as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError(f'{path}: provenance index must contain a JSON object')
    return data
