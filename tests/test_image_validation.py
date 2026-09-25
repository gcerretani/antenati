from __future__ import annotations

import pytest

from antenati.errors import ImageValidationError
from antenati.image import validate_image_bytes
from tests.conftest import TINY_JPEG


def test_html_200_payload_is_rejected() -> None:
    with pytest.raises(ImageValidationError, match='Unsupported image media type'):
        validate_image_bytes('text/html', b'<html>blocked</html>')


def test_corrupt_jpeg_payload_is_rejected() -> None:
    with pytest.raises(ImageValidationError, match='Invalid or corrupt'):
        validate_image_bytes('image/jpeg', b'not-a-jpeg')


def test_mime_signature_mismatch_is_rejected() -> None:
    png = b'\x89PNG\r\n\x1a\n' + b'payload'
    with pytest.raises(ImageValidationError, match='media type mismatch'):
        validate_image_bytes('image/jpeg', png)


def test_valid_supported_jpeg_is_accepted() -> None:
    assert validate_image_bytes('image/jpeg', TINY_JPEG) == '.jpg'
