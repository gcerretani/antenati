# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Filesystem helpers for robust atomic writes."""

from __future__ import annotations

import os
import time
from os import PathLike

_IS_WINDOWS = os.name == 'nt'
_REPLACE_ATTEMPTS = 10
_INITIAL_RETRY_DELAY = 0.02
_MAX_RETRY_DELAY = 0.5
_TRANSIENT_WINDOWS_ERRORS = {5, 32}


def atomic_replace(source: str | PathLike[str], destination: str | PathLike[str]) -> None:
    """Atomically replace the destination, retrying transient Windows locks.

    Antivirus scanners, indexers and preview handlers can briefly open freshly
    written files without delete sharing. Windows then reports access denied or
    sharing violation for an otherwise valid os.replace. Retry only those
    Windows-specific transient errors; all other failures remain immediate.
    """
    delay = _INITIAL_RETRY_DELAY
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(source, destination)
            return
        except OSError as exc:
            transient = _IS_WINDOWS and getattr(exc, 'winerror', None) in _TRANSIENT_WINDOWS_ERRORS
            if not transient or attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, _MAX_RETRY_DELAY)
