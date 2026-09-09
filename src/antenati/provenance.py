# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistent provenance metadata and resume verification."""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Collection
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

MANIFEST_FILENAME = '.antenati-manifest.json'
INDEX_FILENAME = '.antenati-index.json'
INDEX_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ImageRecord:
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

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> ImageRecord:
        try:
            return cls(
                canvas_id=str(value['canvas_id']),
                label=str(value['label']),
                source_url=str(value['source_url']),
                filename=str(value['filename']),
                requested_size=int(value['requested_size']),
                byte_size=int(value['byte_size']),
                sha256=str(value['sha256']),
                downloaded_at=str(value['downloaded_at']),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('Invalid image record in provenance index') from exc


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_record(directory: Path, record: ImageRecord) -> bool:
    """Return True only when the indexed local file still matches size/hash."""
    name = record.filename
    if not name or name != Path(name).name:
        return False
    candidate = directory / name
    try:
        stat = candidate.stat()
    except FileNotFoundError:
        return False
    if not candidate.is_file() or stat.st_size != record.byte_size:
        return False
    return file_sha256(candidate) == record.sha256


def _atomic_write_text(path: Path, text: str) -> None:
    temp_name: str | None = None
    try:
        with NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=path.parent,
            prefix=f'.{path.name}.',
            suffix='.tmp',
            delete=False,
        ) as tmp:
            temp_name = tmp.name
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name is not None:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temp_name)


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
    path = directory / INDEX_FILENAME
    if not path.exists():
        return None
    with path.open(encoding='utf-8') as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError(f'{path}: provenance index must contain a JSON object')
    return data


def _indexed_records(
    directory: Path,
    *,
    manifest_url: str,
    requested_size: int,
) -> dict[tuple[str, str], ImageRecord]:
    """Return every record from the index that matches this manifest and resolution."""
    index = read_index(directory)
    if index is None:
        return {}
    if index.get('schema_version') != INDEX_SCHEMA_VERSION:
        return {}
    if index.get('manifest_url') != manifest_url:
        return {}
    if index.get('requested_size') != requested_size:
        return {}

    images = index.get('images', [])
    if not isinstance(images, list):
        return {}
    result: dict[tuple[str, str], ImageRecord] = {}
    for raw in images:
        if not isinstance(raw, dict):
            continue
        try:
            record = ImageRecord.from_mapping(raw)
        except ValueError:
            continue
        result[(record.canvas_id, record.source_url)] = record
    return result


def verified_resume_records(
    directory: Path,
    *,
    manifest_url: str,
    requested_size: int,
) -> dict[tuple[str, str], ImageRecord]:
    """Return only records safe to reuse for this manifest and resolution."""
    candidates = _indexed_records(directory, manifest_url=manifest_url, requested_size=requested_size)
    return {key: record for key, record in candidates.items() if verify_record(directory, record)}


def carry_over_records(
    directory: Path,
    *,
    manifest_url: str,
    requested_size: int,
    exclude_keys: Collection[tuple[str, str]],
) -> list[ImageRecord]:
    """Return previously indexed records outside this run's plan, so a rewrite doesn't drop them."""
    candidates = _indexed_records(directory, manifest_url=manifest_url, requested_size=requested_size)
    return [record for key, record in candidates.items() if key not in exclude_keys]
