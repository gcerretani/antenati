# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lightweight validation for downloaded image payloads."""

from __future__ import annotations

from pathlib import Path

from antenati.errors import ImageValidationError

_SUPPORTED_MIME: dict[str, tuple[str, str]] = {
    'image/jpeg': ('jpeg', '.jpg'),
    'image/png': ('png', '.png'),
    'image/tiff': ('tiff', '.tif'),
    'image/webp': ('webp', '.webp'),
}


def _detect_format(head: bytes, tail: bytes) -> str | None:
    if len(head) >= 3 and head.startswith(b'\xff\xd8\xff') and tail.endswith(b'\xff\xd9'):
        return 'jpeg'
    if head.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if head.startswith((b'II*\x00', b'MM\x00*')):
        return 'tiff'
    if len(head) >= 12 and head.startswith(b'RIFF') and head[8:12] == b'WEBP':
        return 'webp'
    return None


def extension_for_media_type(content_type: str) -> str:
    declared = _SUPPORTED_MIME.get(content_type.lower())
    if declared is None:
        raise ImageValidationError(f'Unsupported image media type: {content_type}')
    return declared[1]


def _validate(content_type: str, head: bytes, tail: bytes) -> str:
    declared = _SUPPORTED_MIME.get(content_type.lower())
    if declared is None:
        raise ImageValidationError(f'Unsupported image media type: {content_type}')
    detected = _detect_format(head, tail)
    if detected is None:
        raise ImageValidationError(f'Invalid or corrupt {content_type} payload')
    expected_format, extension = declared
    if detected != expected_format:
        raise ImageValidationError(f'Image media type mismatch: declared {content_type}, detected {detected}')
    return extension


def validate_image_bytes(content_type: str, data: bytes) -> str:
    """Validate MIME/signature agreement for an in-memory payload."""
    return _validate(content_type, data[:16], data[-16:])


def validate_image_file(content_type: str, path: Path) -> str:
    """Validate a streamed image without loading the complete file into memory."""
    with path.open('rb') as stream:
        head = stream.read(16)
        try:
            stream.seek(-16, 2)
        except OSError:
            stream.seek(0)
        tail = stream.read(16)
    return _validate(content_type, head, tail)
