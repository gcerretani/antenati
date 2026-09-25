# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Machine-readable JSON rendering for the CLI."""

from __future__ import annotations

import json
import sys
from typing import Any

from antenati.config import DownloadConfig
from antenati.downloader import Downloader, DownloadPlan, DownloadReport
from antenati.formatting import plain_text
from antenati.output import ExistingPolicy, planned_path

SCHEMA_VERSION = 1


def _metadata(downloader: Downloader) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for entry in downloader.manifest.get('metadata', []):
        if not isinstance(entry, dict):
            continue
        label = plain_text(entry.get('label', ''))
        value = plain_text(entry.get('value', ''))
        if label or value:
            items.append({'label': label, 'value': value})
    return items


def _base_payload(downloader: Downloader, config: DownloadConfig, policy: ExistingPolicy) -> dict[str, Any]:
    return {
        'schema_version': SCHEMA_VERSION,
        'source': {
            'input_url': config.url,
            'manifest_url': downloader.manifest_url,
            'archive_id': downloader.archive_id,
            'ark_id': downloader.ark_id,
        },
        'register': {
            'selected_pages': downloader.gallery_length,
            'metadata': _metadata(downloader),
        },
        'output': {
            'directory': str(downloader.dirname),
        },
        'options': {
            'size': config.size,
            'first': config.first,
            'last': config.last,
            'workers': config.n_workers,
            'descriptive_names': config.descriptive_names,
            'existing': policy.value,
        },
    }


def plan_payload(downloader: Downloader, config: DownloadConfig) -> dict[str, Any]:
    plan: DownloadPlan = downloader.plan(config.size)
    payload = _base_payload(downloader, config, config.existing_policy)
    payload['operation'] = 'dry-run'
    payload['plan'] = {
        'expected': plan.expected,
        'size': plan.size,
        'items': [
            {
                'position': index,
                'filename': planned_path(downloader.dirname, item).name,
                'label': plain_text(item.canvas.get('label', '')),
                'canvas_id': plain_text(item.canvas.get('@id', '')),
                'source_url': item.source_url,
            }
            for index, item in enumerate(plan.items, start=1)
        ],
    }
    return payload


def report_payload(
    downloader: Downloader,
    config: DownloadConfig,
    policy: ExistingPolicy,
    report: DownloadReport,
) -> dict[str, Any]:
    payload = _base_payload(downloader, config, policy)
    payload['operation'] = 'download'
    payload['result'] = {
        'successful': report.successful,
        'expected': report.expected,
        'attempted': report.attempted,
        'completed': report.completed,
        'skipped': report.skipped,
        'failed': [{'label': failure.label, 'reason': failure.reason} for failure in report.failed],
        'cancelled': report.cancelled,
        'remaining': report.remaining,
        'bytes_written': report.bytes_written,
    }
    return payload


def emit(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write('\n')
