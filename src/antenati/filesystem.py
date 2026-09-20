# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Filesystem helpers for robust atomic writes."""

from __future__ import annotations

import logging
import os
import time
from os import PathLike

logger = logging.getLogger(__name__)

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
            if attempt:
                logger.debug('Atomic replace succeeded after %d retries: %s', attempt, destination)
            return
        except OSError as exc:
            winerror = getattr(exc, 'winerror', None)
            transient = _IS_WINDOWS and winerror in _TRANSIENT_WINDOWS_ERRORS
            if not transient or attempt == _REPLACE_ATTEMPTS - 1:
                logger.debug('Atomic replace failed: %s -> %s', source, destination, exc_info=True)
                raise
            logger.debug(
                'Atomic replace blocked by Windows (WinError %s), retry %d/%d in %.0f ms: %s',
                winerror,
                attempt + 1,
                _REPLACE_ATTEMPTS - 1,
                delay * 1000,
                destination,
            )
            time.sleep(delay)
            delay = min(delay * 2, _MAX_RETRY_DELAY)
