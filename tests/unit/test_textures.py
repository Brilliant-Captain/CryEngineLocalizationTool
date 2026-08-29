from __future__ import annotations

import struct

import pytest

from cryengine_localization.adapters.textures import (
    TextureValidationError,
    parse_dds_header,
    validate_texture_replacement,
)


def dds(width: int = 128, height: int = 32, mips: int = 1, fourcc: bytes = b"DXT5") -> bytes:
    header = [0] * 31
    header[0] = 124
    header[2] = height
    header[3] = width
    header[4] = 4096
    header[6] = mips
    header[18] = 32
    header[19] = 4
    header[20] = int.from_bytes(fourcc, "little")
    return b"DDS " + struct.pack("<31I", *header) + b"payload"


def test_parse_dds_header_reads_dxt5_dimensions_and_alpha() -> None:
    metadata = parse_dds_header(dds())

    assert metadata.width == 128
    assert metadata.height == 32
    assert metadata.mip_count == 1
    assert metadata.fourcc == "DXT5"
    assert metadata.has_alpha is True


def test_texture_validation_rejects_dimensions_mips_format_and_alpha() -> None:
    original = dds()
    with pytest.raises(TextureValidationError, match="dimension"):
        validate_texture_replacement(original, dds(width=64))
    with pytest.raises(TextureValidationError, match="mip"):
        validate_texture_replacement(original, dds(mips=2))
    with pytest.raises(TextureValidationError, match="compression"):
        validate_texture_replacement(original, dds(fourcc=b"DXT1"))
    with pytest.raises(TextureValidationError, match="alpha"):
        validate_texture_replacement(dds(fourcc=b"DXT1"), dds(fourcc=b"DXT1"), require_alpha=True)

