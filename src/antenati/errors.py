# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exception hierarchy for the antenati downloader.

A single base ``AntenatiError`` lets callers catch any tool-specific
error with one ``except`` while still allowing fine-grained handling.
``ManifestError`` is raised by :mod:`antenati.iiif` for malformed gallery
or manifest data; ``WafChallengeError`` is raised by :mod:`antenati.http`
on the SAN server's AWS WAF challenge response.
"""

from __future__ import annotations


class AntenatiError(Exception):
    """Base class for all antenati-specific errors."""


class ManifestError(AntenatiError):
    """The IIIF manifest is missing a required field or has an unexpected shape."""


class WafChallengeError(AntenatiError):
    """The SAN server returned an AWS WAF challenge response that cannot be bypassed."""


class ThreadError(AntenatiError):
    """Container used inside the download thread pool for exception chaining.

    Wraps the original exception so the orchestrator can associate the
    failure with a specific canvas label without losing the cause.
    """

    def __init__(self, label: str):
        super().__init__(label)
        self.label = label
