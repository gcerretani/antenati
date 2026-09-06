# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exception hierarchy for the antenati downloader."""

from __future__ import annotations


class AntenatiError(Exception):
    """Base class for all antenati-specific errors."""


class ManifestError(AntenatiError):
    """The IIIF manifest is missing a required field or has an unexpected shape."""


class ImageValidationError(AntenatiError):
    """A downloaded response is not a supported, internally consistent image."""


class WafChallengeError(AntenatiError):
    """The SAN server returned an AWS WAF challenge response that cannot be bypassed."""


class ThreadError(AntenatiError):
    """Associate a worker failure with a specific canvas label."""

    def __init__(self, label: str):
        super().__init__(label)
        self.label = label
