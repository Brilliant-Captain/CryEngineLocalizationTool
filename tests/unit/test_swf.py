from __future__ import annotations

import zlib

import pytest

from cryengine_localization.adapters.swf import (
    SWF_HEADER_SIZE,
    SwfFormatError,
    build_tag,
    decode_gfx_container,
    encode_gfx_container,
    iter_tags,
    replace_define_font3_tags,
)


def _font_tag(character_id: int, marker: bytes) -> bytes:
    return build_tag(75, character_id.to_bytes(2, "little") + marker)


def _fixture_payload() -> bytes:
    header = bytes(range(SWF_HEADER_SIZE))
    return header + build_tag(9, b"rgb") + _font_tag(1, b"old-font") + build_tag(1, b"") + build_tag(0, b"")


def test_decode_gfx_container_preserves_legacy_header_and_tags() -> None:
    raw = b"GFX\x08" + (8 + len(_fixture_payload())).to_bytes(4, "little") + _fixture_payload()

    container = decode_gfx_container(raw)

    assert container.magic == b"GFX"
    assert container.payload_header == bytes(range(SWF_HEADER_SIZE))
    assert [tag.code for tag in container.tags] == [9, 75, 1, 0]


def test_decode_cfx_container_decompresses_after_outer_header() -> None:
    payload = _fixture_payload()
    raw = b"CFX\x0f" + (8 + len(payload)).to_bytes(4, "little") + zlib.compress(payload, 9)

    container = decode_gfx_container(raw)

    assert container.magic == b"CFX"
    assert container.compressed is True
    assert container.payload == payload


def test_iter_tags_supports_long_tag_lengths() -> None:
    body = b"x" * 100
    payload = bytes(range(SWF_HEADER_SIZE)) + build_tag(75, body) + build_tag(0, b"")

    tags = list(iter_tags(payload))

    assert tags[0].code == 75
    assert tags[0].payload == body
    assert tags[0].header_size == 6


def test_replace_define_font3_tags_changes_only_requested_font_tag() -> None:
    original = _fixture_payload()
    candidate = bytes(range(SWF_HEADER_SIZE)) + build_tag(9, b"rgb") + _font_tag(1, b"new-font") + build_tag(1, b"") + build_tag(0, b"")

    result = replace_define_font3_tags(original, candidate, {1})

    original_tags = list(iter_tags(original))
    result_tags = list(iter_tags(result))
    assert result_tags[0].raw == original_tags[0].raw
    assert result_tags[1].raw != original_tags[1].raw
    assert result_tags[2].raw == original_tags[2].raw
    assert result_tags[3].raw == original_tags[3].raw


def test_replace_rejects_non_font_tag_changes() -> None:
    original = _fixture_payload()
    candidate = bytes(range(SWF_HEADER_SIZE)) + build_tag(9, b"changed") + _font_tag(1, b"new-font") + build_tag(1, b"") + build_tag(0, b"")

    with pytest.raises(SwfFormatError, match="non-font tag"):
        replace_define_font3_tags(original, candidate, {1})


def test_replace_can_keep_original_non_font_tags_for_migration() -> None:
    original = _fixture_payload()
    candidate = bytes(range(SWF_HEADER_SIZE)) + build_tag(9, b"changed") + _font_tag(1, b"new-font") + build_tag(1, b"") + build_tag(0, b"")

    result = replace_define_font3_tags(original, candidate, {1}, require_non_font_identity=False)

    assert list(iter_tags(result))[0].raw == list(iter_tags(original))[0].raw
    assert list(iter_tags(result))[1].payload.endswith(b"new-font")


def test_encode_gfx_container_updates_outer_uncompressed_length() -> None:
    payload = _fixture_payload()
    raw = b"GFX\x08" + (8 + len(payload)).to_bytes(4, "little") + payload
    container = decode_gfx_container(raw)
    expanded = payload[:-2] + build_tag(1, b"x") + build_tag(0, b"")
    rebuilt = encode_gfx_container(container, expanded)

    assert rebuilt[:4] == raw[:4]
    assert int.from_bytes(rebuilt[4:8], "little") == len(rebuilt)
