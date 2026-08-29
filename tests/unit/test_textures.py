from __future__ import annotations

import struct
import zlib

import pytest

from cryengine_localization.adapters.textures import (
    TextureValidationError,
    parse_dds_header,
    encode_rgba_to_dds,
    read_image_rgba,
    replace_texture_in_pak,
    validate_texture_replacement,
)
from cryengine_localization.adapters.pak import build_pak


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


def test_replace_texture_in_pak_preserves_entry_path_and_metadata(tmp_path) -> None:
    source = tmp_path / "source.pak"
    output = tmp_path / "output.pak"
    original = dds()
    replacement = dds()
    build_pak({"ui/menu.dds": original, "ui/other.txt": b"keep"}, source)

    replace_texture_in_pak(source, r"ui\menu.dds", replacement, output)

    import zipfile

    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == ["ui/menu.dds", "ui/other.txt"]
        assert parse_dds_header(archive.read("ui/menu.dds")).fourcc == "DXT5"


def test_pure_python_encoder_writes_dxt5_with_full_mip_chain() -> None:
    pixels = bytes([255, 0, 0, 255] * 16)

    encoded = encode_rgba_to_dds(4, 4, pixels, mipmaps=True)
    metadata = parse_dds_header(encoded)

    assert metadata.width == 4
    assert metadata.height == 4
    assert metadata.mip_count == 3
    assert metadata.fourcc == "DXT5"
    assert metadata.has_alpha is True
    assert len(encoded) == 128 + 16 + 16 + 16


def test_pure_python_encoder_avoids_dxt1_transparency_mode_for_solid_white() -> None:
    encoded = encode_rgba_to_dds(4, 4, bytes([255, 255, 255, 255] * 16), mipmaps=False)
    color_endpoint_0, color_endpoint_1 = struct.unpack_from("<HH", encoded, 128 + 8)

    assert color_endpoint_0 > color_endpoint_1


def test_png_reader_is_available_without_pillow(tmp_path) -> None:
    def chunk(name: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", zlib.crc32(name + payload) & 0xFFFFFFFF)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\x0a\x14\x1e\xff"))
        + chunk(b"IEND", b"")
    )
    path = tmp_path / "pixel.png"
    path.write_bytes(png)

    image = read_image_rgba(path)

    assert (image.width, image.height, image.pixels) == (1, 1, bytes([10, 20, 30, 255]))


def test_binary_ppm_reader_keeps_whitespace_valued_first_pixel(tmp_path) -> None:
    path = tmp_path / "pixel.ppm"
    path.write_bytes(b"P6\n1 1\n255\n" + bytes([32, 10, 20]))

    image = read_image_rgba(path)

    assert image.pixels == bytes([32, 10, 20, 255])
