# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Output-directory and existing-file policy helpers."""

from __future__ import annotations

import threading
from enum import Enum
from pathlib import Path
from urllib.parse import urlsplit

from antenati import provenance
from antenati.downloader import Downloader, DownloadItem, DownloadReport, ProgressBar


class ExistingPolicy(str, Enum):
    """How to handle a destination that already contains planned files."""

    ERROR = 'error'
    OVERWRITE = 'overwrite'
    SKIP = 'skip'
    RESUME = 'resume'


def planned_path(directory: Path, item: DownloadItem) -> Path:
    """Return the expected local image path without requesting the body."""
    suffix = Path(urlsplit(item.source_url).path).suffix.lower()
    if suffix in {'.jpeg', '.jpe'}:
        suffix = '.jpg'
    if suffix == '.tiff':
        suffix = '.tif'
    if suffix not in {'.jpg', '.png', '.tif', '.webp'}:
        suffix = '.img'
    return directory / f'{item.stem}{suffix}'


def prepare_output(downloader: Downloader, output: str | Path | None, policy: ExistingPolicy) -> Path:
    """Resolve/create the exact destination directory according to ``policy``."""
    directory = Path(output) if output is not None else downloader.dirname
    downloader.dirname = directory
    if directory.exists():
        if not directory.is_dir():
            raise RuntimeError(f'Output path is not a directory: {directory}')
        if policy is ExistingPolicy.ERROR and any(directory.iterdir()):
            raise RuntimeError(f'Output directory already exists and is not empty: {directory}')
    else:
        directory.mkdir(parents=True)
    return directory


def _validate_skip_policy(downloader: Downloader, size: int) -> None:
    """Refuse to overwrite an existing unverified file under ``skip`` policy."""
    plan = downloader.plan(size)
    verified = provenance.verified_resume_records(
        downloader.dirname,
        manifest_url=downloader.manifest_url,
        requested_size=size,
    )
    verified_keys = set(verified)
    for item in plan.items:
        candidate = planned_path(downloader.dirname, item)
        key = (str(item.canvas.get('@id', '')), item.source_url)
        if candidate.exists() and key not in verified_keys:
            raise RuntimeError(
                f'{candidate}: existing file is not verified for this source/resolution; use resume to verify/redownload it or overwrite to replace it'
            )


def run_with_policy(
    downloader: Downloader,
    *,
    n_workers: int,
    size: int,
    progress: ProgressBar,
    policy: ExistingPolicy,
    cancel: threading.Event | None = None,
) -> DownloadReport:
    """Execute with deterministic existing-file semantics.

    ``error`` is enforced while preparing the directory. ``overwrite`` always
    downloads planned pages. ``resume`` reuses only hash-verified provenance
    and redownloads stale/corrupt files. ``skip`` also reuses verified files,
    but refuses to overwrite an unverified file that already occupies a
    planned path.
    """
    if policy is ExistingPolicy.SKIP:
        _validate_skip_policy(downloader, size)
    return downloader.run(
        n_workers=n_workers,
        size=size,
        progress=progress,
        cancel=cancel,
        resume=policy in {ExistingPolicy.RESUME, ExistingPolicy.SKIP},
    )
