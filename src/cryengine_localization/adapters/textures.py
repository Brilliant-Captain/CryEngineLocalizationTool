"""DDS metadata validation and PAK replacement helpers."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class TextureFormatError(ValueError):
    """Input is not a supported DDS file."""


class TextureValidationError(ValueError):
    """Replacement metadata is incompatible with the source texture."""


@dataclass(frozen=True)
class DdsMetadata:
    width: int
    height: int
    mip_count: int
    fourcc: str
    has_alpha: bool
    rgb_bit_count: int
    pitch_or_linear: int


def parse_dds_header(raw: bytes) -> DdsMetadata:
    if len(raw) < 128 or raw[:4] != b"DDS ":
        raise TextureFormatError("missing DDS magic or header")
    values = struct.unpack_from("<31I", raw, 4)
    if values[0] != 124:
        raise TextureFormatError("invalid DDS header size")
    height, width, pitch, mip_count = values[2], values[3], values[4], values[6] or 1
    pixel_format_size, pixel_flags, fourcc_value, rgb_bits, _r, _g, _b, alpha_mask = values[18:26]
    if pixel_format_size != 32:
        raise TextureFormatError("invalid DDS pixel format size")
    fourcc = fourcc_value.to_bytes(4, "little").decode("latin1")
    has_alpha = alpha_mask != 0 or fourcc in {"DXT3", "DXT5", "BC2 ", "BC3 "}
    return DdsMetadata(width, height, mip_count, fourcc, has_alpha, rgb_bits, pitch)


def validate_texture_replacement(
    original: bytes, replacement: bytes, *, require_alpha: bool = False
) -> DdsMetadata:
    source = parse_dds_header(original)
    candidate = parse_dds_header(replacement)
    errors: list[str] = []
    if (candidate.width, candidate.height) != (source.width, source.height):
        errors.append("dimension mismatch")
    if candidate.mip_count != source.mip_count:
        errors.append("mip count mismatch")
    if candidate.fourcc != source.fourcc:
        errors.append("compression format mismatch")
    if require_alpha and not candidate.has_alpha:
        errors.append("alpha channel required")
    if errors:
        raise TextureValidationError("; ".join(errors))
    return candidate


def replace_texture_in_pak(
    source_pak: str | Path,
    entry_path: str,
    replacement: bytes | str | Path,
    output_pak: str | Path,
    *,
    require_alpha: bool = False,
) -> Path:
    from zipfile import ZipFile

    from cryengine_localization.adapters.pak import build_pak, normalize_entry_path, scan_pak

    archive = scan_pak(source_pak)
    normalized_requested = normalize_entry_path(entry_path)
    normalized = next((entry.path for entry in archive.entries if entry.path == normalized_requested), None)
    if normalized is None:
        raise KeyError(entry_path)
    replacement_bytes = Path(replacement).read_bytes() if isinstance(replacement, (str, Path)) else bytes(replacement)
    with ZipFile(archive.path, "r") as source:
        payload = {entry.path: source.read(entry.source_name) for entry in archive.entries}
    validate_texture_replacement(payload[normalized], replacement_bytes, require_alpha=require_alpha)
    payload[normalized] = replacement_bytes
    return build_pak(payload, output_pak)
