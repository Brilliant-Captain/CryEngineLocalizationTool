from __future__ import annotations

from pathlib import Path

import pytest

from cryengine_localization.adapters.gfxfont import (
    FontCoverage,
    FontSlot,
    GfxFormatError,
    GfxToolError,
    assess_gfx_safety,
    build_font_replace_command,
    compare_gfx_rebuilds,
    inspect_font_coverage,
    replace_font_slots_in_place,
    parse_ffdec_font_dump,
    replace_font_slots,
    scan_gfx_fonts,
    subset_font,
    validate_gfx_bytes,
)
from cryengine_localization.adapters.swf import SWF_HEADER_SIZE, build_tag


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


def test_gfx_validation_and_scan_accept_gfx_container(tmp_path, monkeypatch) -> None:
    path = tmp_path / "legacy.gfx"
    raw = b"GFX" + b"\x00" * 9
    path.write_bytes(raw)

    class Completed:
        stdout = 'DefineFont3 (chid: 1, fn: "Noto Sans")\nExportAssets (chid: 1, exp: "Font_Body")'
        stderr = ""

    monkeypatch.setattr(
        "cryengine_localization.adapters.gfxfont.subprocess.run",
        lambda *args, **kwargs: Completed(),
    )

    assert validate_gfx_bytes(raw) == raw
    assert scan_gfx_fonts(path, "ffdec-cli.exe") == (FontSlot(1, "Noto Sans", "Font_Body"),)


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


def test_replace_font_slots_stages_ffdec_output_outside_destination_directory(tmp_path, monkeypatch) -> None:
    source = tmp_path / "input.gfx"
    source.write_bytes(b"GFX" + b"\x00" * 9)
    font = tmp_path / "font.ttf"
    font.write_bytes(b"font")
    destination = tmp_path / "deep" / "nested" / "output.gfx"
    stages: list[Path] = []

    monkeypatch.setattr(
        "cryengine_localization.adapters.gfxfont.scan_gfx_fonts",
        lambda *_args, **_kwargs: (FontSlot(1, "Body"),),
    )

    def fake_run(command, **_kwargs):
        stage = Path(command[3])
        stages.append(stage)
        stage.write_bytes(b"GFX" + b"\x00" * 9)

    monkeypatch.setattr("cryengine_localization.adapters.gfxfont.subprocess.run", fake_run)

    assert replace_font_slots(source, destination, {1: font}, ffdec_cli="ffdec") == destination
    assert destination.is_file()
    assert len(stages) == 1
    assert stages[0].parent != destination.parent


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


def _legacy_gfx_payload(font_marker: bytes = b"font", *, changed_shape: bool = False) -> bytes:
    header = bytes(range(SWF_HEADER_SIZE))
    shape = b"changed" if changed_shape else b"shape"
    return header + build_tag(9, shape) + build_tag(75, (1).to_bytes(2, "little") + font_marker) + build_tag(0, b"")


def test_assess_gfx_safety_flags_small_compressed_font_file(tmp_path) -> None:
    import zlib

    path = tmp_path / "small.cfx"
    payload = _legacy_gfx_payload(b"font")
    path.write_bytes(b"CFX\x0f" + (8 + len(payload)).to_bytes(4, "little") + zlib.compress(payload, 9))

    report = assess_gfx_safety(path)

    assert report.level == "caution"
    assert any("small compressed" in reason for reason in report.reasons)


def test_compare_gfx_rebuilds_allows_font_only_change(tmp_path) -> None:
    original = tmp_path / "original.gfx"
    candidate = tmp_path / "candidate.gfx"
    header = b"GFX\x08" + (8 + len(_legacy_gfx_payload())).to_bytes(4, "little")
    original.write_bytes(header + _legacy_gfx_payload())
    candidate.write_bytes(header + _legacy_gfx_payload(b"new-font"))

    comparison = compare_gfx_rebuilds(original, candidate, {1})

    assert comparison.non_font_changes == ()
    assert comparison.changed_font_ids == (1,)
    assert comparison.level != "blocked"


def test_assess_gfx_safety_blocks_non_font_candidate_change(tmp_path) -> None:
    original = tmp_path / "original.gfx"
    candidate = tmp_path / "candidate.gfx"
    original_payload = _legacy_gfx_payload()
    candidate_payload = _legacy_gfx_payload(b"new-font", changed_shape=True)
    original.write_bytes(b"GFX\x08" + (8 + len(original_payload)).to_bytes(4, "little") + original_payload)
    candidate.write_bytes(b"GFX\x08" + (8 + len(candidate_payload)).to_bytes(4, "little") + candidate_payload)

    report = assess_gfx_safety(original, candidate_path=candidate)

    assert report.level == "blocked"
    assert any("non-font" in reason for reason in report.reasons)


def test_replace_font_slots_in_place_keeps_original_non_font_tags(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.gfx"
    output = tmp_path / "output.gfx"
    font = tmp_path / "font.ttf"
    source_payload = _legacy_gfx_payload(b"old", changed_shape=False)
    candidate_payload = _legacy_gfx_payload(b"new", changed_shape=True)
    source.write_bytes(b"GFX\x08" + (8 + len(source_payload)).to_bytes(4, "little") + source_payload)
    font.write_bytes(b"font")

    monkeypatch.setattr(
        "cryengine_localization.adapters.gfxfont.scan_gfx_fonts",
        lambda *_args, **_kwargs: (FontSlot(1, "_typewriter"),),
    )

    def fake_run(command, **_kwargs):
        Path(command[3]).write_bytes(b"GFX\x08" + (8 + len(candidate_payload)).to_bytes(4, "little") + candidate_payload)

    monkeypatch.setattr("cryengine_localization.adapters.gfxfont.subprocess.run", fake_run)

    replace_font_slots_in_place(source, output, {1: font}, ffdec_cli="ffdec")

    result_tags = list(__import__("cryengine_localization.adapters.swf", fromlist=["iter_tags"]).iter_tags(__import__("cryengine_localization.adapters.swf", fromlist=["decode_gfx_container"]).decode_gfx_container(output.read_bytes()).payload))
    source_tags = list(__import__("cryengine_localization.adapters.swf", fromlist=["iter_tags"]).iter_tags(__import__("cryengine_localization.adapters.swf", fromlist=["decode_gfx_container"]).decode_gfx_container(source.read_bytes()).payload))
    assert result_tags[0].raw == source_tags[0].raw
    assert result_tags[1].payload.endswith(b"new")
