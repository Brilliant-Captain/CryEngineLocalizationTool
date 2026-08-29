from __future__ import annotations

import pytest

from cryengine_localization.adapters.gfxfont import (
    GfxFormatError,
    build_font_replace_command,
    parse_ffdec_font_dump,
    validate_gfx_bytes,
)


def test_parse_ffdec_dump_discovers_font_slots_and_exports() -> None:
    dump = '\n'.join(
        [
            'DefineFont3 (chid: 7, fn: "Type No. 12 WF") tagId= 75',
            'ExportAssets (chid: 7, exp: "wor_TypeNo.12WF") tagId= 56',
            'DefineFont3 (chid: 16, fn: "Type No. 2 WF") tagId= 75',
            'ExportAssets (chid: 16, exp: "wor_TypeNo.2WF") tagId= 56',
        ]
    )

    slots = parse_ffdec_font_dump(dump)

    assert [(slot.character_id, slot.font_name, slot.export_name) for slot in slots] == [
        (7, "Type No. 12 WF", "wor_TypeNo.12WF"),
        (16, "Type No. 2 WF", "wor_TypeNo.2WF"),
    ]


def test_gfx_validation_rejects_non_cfx() -> None:
    with pytest.raises(GfxFormatError):
        validate_gfx_bytes(b"not-gfx")


def test_font_replace_command_has_dynamic_id_and_no_shell() -> None:
    command = build_font_replace_command("ffdec-cli.exe", "in.gfx", "out.gfx", 7, "font.ttf")

    assert command == ["ffdec-cli.exe", "-replace", "in.gfx", "out.gfx", "7", "font.ttf"]

