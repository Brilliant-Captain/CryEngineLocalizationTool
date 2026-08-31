"""Small, conservative parser for the legacy Scaleform GFX/CFX containers."""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass


OUTER_HEADER_SIZE = 8
# Legacy Scaleform GFX files used by CryEngine keep a 13-byte movie header
# after the outer GFX/CFX header.  FFDec reports the first tag at file offset
# 0x15 (8-byte outer header + 13-byte movie header).
SWF_HEADER_SIZE = 13
DEFINE_FONT3_TAG = 75


class SwfFormatError(ValueError):
    """The legacy GFX/CFX payload cannot be safely interpreted."""


@dataclass(frozen=True)
class SwfTag:
    code: int
    payload: bytes
    raw: bytes
    offset: int
    header_size: int


@dataclass(frozen=True)
class GfxContainer:
    magic: bytes
    outer_header: bytes
    payload: bytes
    payload_header: bytes
    tags: tuple[SwfTag, ...]
    compressed: bool


def build_tag(code: int, payload: bytes = b"") -> bytes:
    """Encode one SWF tag using the short or long length form."""

    if not 0 <= code <= 0x3FF:
        raise ValueError("tag code must fit in 10 bits")
    length = len(payload)
    if length < 0x3F:
        return struct.pack("<H", (code << 6) | length) + payload
    return struct.pack("<H", (code << 6) | 0x3F) + struct.pack("<I", length) + payload


def iter_tags(payload: bytes):
    """Yield tags after the 13-byte legacy Scaleform movie header."""

    if len(payload) < SWF_HEADER_SIZE:
        raise SwfFormatError("payload is shorter than the legacy Scaleform header")
    position = SWF_HEADER_SIZE
    while position < len(payload):
        start = position
        if position + 2 > len(payload):
            raise SwfFormatError(f"truncated tag header at offset 0x{position:X}")
        record = struct.unpack_from("<H", payload, position)[0]
        position += 2
        code = record >> 6
        short_length = record & 0x3F
        header_size = 2
        if short_length == 0x3F:
            if position + 4 > len(payload):
                raise SwfFormatError(f"truncated long tag length at offset 0x{position:X}")
            length = struct.unpack_from("<I", payload, position)[0]
            position += 4
            header_size = 6
        else:
            length = short_length
        end = position + length
        if end > len(payload):
            raise SwfFormatError(
                f"tag {code} at offset 0x{start:X} exceeds payload ({length} bytes)"
            )
        raw = payload[start:end]
        yield SwfTag(code, payload[position:end], raw, start, header_size)
        position = end
        if code == 0:
            if length != 0:
                raise SwfFormatError("End tag must have an empty payload")
            if position != len(payload):
                raise SwfFormatError("bytes found after End tag")
            break
    if position != len(payload):
        raise SwfFormatError("tag stream did not consume the complete payload")


def decode_gfx_container(raw: bytes) -> GfxContainer:
    """Decode a legacy GFX/CFX file while retaining its outer header."""

    if len(raw) < OUTER_HEADER_SIZE:
        raise SwfFormatError("file is shorter than the GFX/CFX outer header")
    magic = raw[:3]
    if magic not in (b"GFX", b"CFX"):
        raise SwfFormatError("unsupported GFX/CFX signature")
    outer_header = raw[:OUTER_HEADER_SIZE]
    compressed = magic == b"CFX"
    try:
        payload = zlib.decompress(raw[OUTER_HEADER_SIZE:]) if compressed else raw[OUTER_HEADER_SIZE:]
    except zlib.error as exc:
        raise SwfFormatError("invalid CFX zlib payload") from exc
    if len(payload) < SWF_HEADER_SIZE:
        raise SwfFormatError("payload is shorter than the legacy Scaleform header")
    tags = tuple(iter_tags(payload))
    return GfxContainer(
        magic=magic,
        outer_header=outer_header,
        payload=payload,
        payload_header=payload[:SWF_HEADER_SIZE],
        tags=tags,
        compressed=compressed,
    )


def encode_gfx_container(container: GfxContainer, payload: bytes) -> bytes:
    """Re-encode a container, preserving its outer format and metadata."""

    if len(payload) < SWF_HEADER_SIZE:
        raise SwfFormatError("payload is shorter than the legacy Scaleform header")
    tuple(iter_tags(payload))
    header = bytearray(container.outer_header)
    if len(header) != OUTER_HEADER_SIZE:
        raise SwfFormatError("invalid stored outer header")
    uncompressed_length = OUTER_HEADER_SIZE + len(payload)
    header[4:8] = struct.pack("<I", uncompressed_length)
    body = zlib.compress(payload, 9) if container.compressed else payload
    return bytes(header) + body


def replace_define_font3_tags(
    original_payload: bytes,
    candidate_payload: bytes,
    character_ids: set[int] | frozenset[int],
    *,
    require_non_font_identity: bool = True,
) -> bytes:
    """Copy selected DefineFont3 tags from a candidate into the original payload.

    When ``require_non_font_identity`` is true, every non-target tag must be
    byte-identical in both payloads. This prevents a full FFDec rebuild from
    silently changing timelines, shapes, or scripts. The in-place migration
    backend can disable that comparison because it deliberately keeps the
    original non-font tags and copies only the selected font tags.
    """

    if original_payload[:SWF_HEADER_SIZE] != candidate_payload[:SWF_HEADER_SIZE]:
        raise SwfFormatError("internal Scaleform headers differ")
    original_tags = list(iter_tags(original_payload))
    candidate_tags = list(iter_tags(candidate_payload))
    if len(original_tags) != len(candidate_tags):
        raise SwfFormatError("tag counts differ between original and candidate")

    wanted = set(character_ids)
    found: set[int] = set()
    output: list[bytes] = [original_payload[:SWF_HEADER_SIZE]]
    for original, candidate in zip(original_tags, candidate_tags):
        if original.code != candidate.code:
            raise SwfFormatError("tag order or code differs between original and candidate")
        is_font = original.code == DEFINE_FONT3_TAG
        font_id = int.from_bytes(original.payload[:2], "little") if is_font and len(original.payload) >= 2 else None
        if is_font and font_id in wanted:
            if len(candidate.payload) < 2 or int.from_bytes(candidate.payload[:2], "little") != font_id:
                raise SwfFormatError(f"candidate DefineFont3 ID does not match {font_id}")
            output.append(candidate.raw)
            found.add(font_id)
        else:
            if require_non_font_identity and original.raw != candidate.raw:
                label = "font" if is_font else "non-font"
                raise SwfFormatError(f"{label} tag changed outside requested IDs")
            output.append(original.raw)
    missing = sorted(wanted - found)
    if missing:
        raise SwfFormatError(f"requested DefineFont3 ID(s) not found: {missing}")
    result = b"".join(output)
    tuple(iter_tags(result))
    return result
