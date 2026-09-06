# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lightweight validation for downloaded image payloads."""

from __future__ import annotations

from antenati.errors import ImageValidationError

_SUPPORTED_MIME: dict[str, tuple[str, str]] = {
    'image/jpeg': ('jpeg', '.jpg'),
    'image/png': ('png', '.png'),
    'image/tiff': ('tiff', '.tif'),
    'image/webp': ('webp', '.webp'),
}


def _detect_format(data: bytes) -> str | None:
    if len(data) >= 4 and data.startswith(b'\xff\xd8\xff') and data.endswith(b'\xff\xd9'):
        return 'jpeg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if data.startswith((b'II*\x00', b'MM\x00*')):
        return 'tiff'
    if len(data) >= 12 and data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        return 'webp'
    return None


def validate_image_bytes(content_type: str, data: bytes) -> str:
    """Validate MIME/signature agreement and return the canonical extension."""
    declared = _SUPPORTED_MIME.get(content_type.lower())
    if declared is None:
        raise ImageValidationError(f'Unsupported image media type: {content_type}')
    detected = _detect_format(data)
    if detected is None:
        raise ImageValidationError(f'Invalid or corrupt {content_type} payload')
    expected_format, extension = declared
    if detected != expected_format:
        raise ImageValidationError(
            f'Image media type mismatch: declared {content_type}, detected {detected}'
        )
    return extension
