from __future__ import annotations

from pathlib import Path

import pytest

from cryengine_localization.adapters.gfxfont import (
    FontCoverage,
    GfxFormatError,
    GfxToolError,
    build_font_replace_command,
    inspect_font_coverage,
    parse_ffdec_font_dump,
    replace_font_slots,
    subset_font,
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


def test_replace_font_slots_rejects_unknown_slot_before_writing(tmp_path, monkeypatch) -> None:
    source = tmp_path / "input.gfx"
    source.write_bytes(b"CFX" + b"\x00" * 5)
    font = tmp_path / "font.ttf"
    font.write_bytes(b"font")
    monkeypatch.setattr(
        "cryengine_localization.adapters.gfxfont.scan_gfx_fonts",
        lambda *_args, **_kwargs: (type("Slot", (), {"character_id": 7})(),),
    )

    with pytest.raises(GfxToolError, match="not found"):
        replace_font_slots(source, tmp_path / "output.gfx", {16: font}, ffdec_cli="ffdec")
    assert not (tmp_path / "output.gfx").exists()


def test_inspect_font_coverage_uses_external_runner(tmp_path, monkeypatch) -> None:
    text = tmp_path / "text.txt"
    text.write_text("中文A", encoding="utf-8")

    class Completed:
        stdout = '{"character_count": 3, "supported_count": 2, "missing": ["文"]}'

    monkeypatch.setattr(
        "cryengine_localization.adapters.gfxfont.subprocess.run",
        lambda *args, **kwargs: Completed(),
    )

    coverage = inspect_font_coverage("font.ttf", text, python_executable="python")

    assert coverage == FontCoverage(3, 2, ("文",))


def test_inspect_font_coverage_defaults_to_bundled_fonttools(monkeypatch) -> None:
    expected = FontCoverage(2, 2, ())
    monkeypatch.setattr(
        "cryengine_localization.adapters.gfxfont._inspect_font_coverage_in_process",
        lambda *_args: expected,
    )
    monkeypatch.setattr(
        "cryengine_localization.adapters.gfxfont.subprocess.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("external Python must not run")),
    )

    assert inspect_font_coverage("font.ttf", "text.txt") == expected


def test_subset_font_defaults_to_bundled_fonttools(monkeypatch) -> None:
    expected = Path("subset.ttf")
    monkeypatch.setattr(
        "cryengine_localization.adapters.gfxfont._subset_font_in_process",
        lambda *_args: expected,
    )
    monkeypatch.setattr(
        "cryengine_localization.adapters.gfxfont.subprocess.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("external Python must not run")),
    )

    assert subset_font("font.ttf", "text.txt", "subset.ttf") == expected
