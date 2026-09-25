# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exception hierarchy for the antenati downloader."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from antenati.downloader import DownloadReport


class AntenatiError(Exception):
    """Base class for all antenati-specific errors."""


class ValidationError(AntenatiError):
    """User-supplied download options are invalid."""


class ManifestError(AntenatiError):
    """The IIIF manifest is missing a required field or has an unexpected shape."""


class ImageValidationError(AntenatiError):
    """A downloaded response is not a supported, internally consistent image."""


class HttpMetadataError(AntenatiError):
    """An HTTP response is missing required metadata."""


class ResourceLimitError(AntenatiError):
    """A configured safety limit was exceeded."""


class UrlTrustError(AntenatiError):
    """A network URL violates the active Antenati trust policy."""


class WafChallengeError(AntenatiError):
    """The SAN server returned an AWS WAF challenge response that cannot be bypassed."""


class DownloadFailedError(AntenatiError):
    """A strict download run completed with an unsuccessful report."""

    def __init__(self, report: DownloadReport):
        super().__init__(
            'Download did not complete successfully '
            f'(completed={report.completed}, skipped={report.skipped}, failed={len(report.failed)}, cancelled={report.cancelled})'
        )
        self.report = report


class ThreadError(AntenatiError):
    """Associate a worker failure with a specific canvas label."""

    def __init__(self, label: str):
        super().__init__(label)
        self.label = label
