from __future__ import annotations

from dataclasses import replace

import pytest

from cryengine_localization.adapters.batch_resources import scan_game_resources
from cryengine_localization.adapters.pak import build_pak, read_pak_members
from cryengine_localization.adapters.gfxfont import FontSlot, GfxNoFontSlotsError, GfxToolError
from cryengine_localization.core.batch_workflow import build_batch_font_overlay, build_batch_translation_overlay
from cryengine_localization.io.json_localization import parse_json_relaxed


def _game_root(tmp_path):
    root = tmp_path / "game"
    assets = root / "Assets"
    assets.mkdir(parents=True)
    build_pak(
        {"Localization/english/MainMenu.json": b'{"Localizations":[{"key":"ui_start","value":"Start"}]}'},
        assets / "a.pak",
    )
    build_pak(
        {"Localization/english/Dialog.json": b'{"Localizations":[{"key":"ui_exit","value":"Exit"}]}'},
        assets / "b.pak",
    )
    build_pak({"Libs/UI/MainMenu.gfx": b"GFX\x08\x00\x00\x00\x00Main Menu\x00"}, assets / "ui.pak")
    return root


def test_build_batch_translation_overlay_preserves_virtual_member_names(tmp_path) -> None:
    root = _game_root(tmp_path)
    scan = scan_game_resources(root)
    entries = [
        replace(entry, translation={"ui_start": "开始", "ui_exit": "退出"}.get(entry.text_key, ""))
        for entry in scan.catalog
    ]
    report_only = next(entry for entry in entries if entry.status == "report-only")
    entries[entries.index(report_only)] = replace(report_only, translation="主菜单")
    output = tmp_path / "out" / "zzz_translation.pak"

    report = build_batch_translation_overlay(root, entries, output)

    assert report.output_pak == output.resolve()
    assert report.written_paths == (
        "Localization/english/Dialog.json",
        "Localization/english/MainMenu.json",
    )
    assert report.skipped_report_only == (report_only.resource_id,)
    members = read_pak_members(output, report.written_paths)
    assert parse_json_relaxed(members["Localization/english/MainMenu.json"])["Localizations"][0]["value"] == "开始"
    assert parse_json_relaxed(members["Localization/english/Dialog.json"])["Localizations"][0]["value"] == "退出"
    assert all(not path.endswith(".gfx") for path in members)


def test_build_batch_translation_overlay_rejects_virtual_path_collisions_before_output(tmp_path) -> None:
    root = tmp_path / "game"
    assets = root / "Assets"
    assets.mkdir(parents=True)
    payload = b'{"Localizations":[{"key":"ui_start","value":"Start"}]}'
    build_pak({"Localization/english/MainMenu.json": payload}, assets / "a.pak")
    build_pak({"Localization/english/MainMenu.json": payload}, assets / "b.pak")
    entries = [replace(entry, translation="开始") for entry in scan_game_resources(root).catalog]
    output = tmp_path / "out.pak"

    with pytest.raises(ValueError, match="multiple source archives"):
        build_batch_translation_overlay(root, entries, output)

    assert not output.exists()


def test_build_batch_translation_overlay_rejects_output_inside_game_root(tmp_path) -> None:
    root = _game_root(tmp_path)
    entries = [replace(entry, translation="开始") for entry in scan_game_resources(root).catalog if entry.status == "active"]

    with pytest.raises(ValueError, match="outside the game root"):
        build_batch_translation_overlay(root, entries, root / "Assets" / "patch.pak")


def test_build_batch_font_overlay_replaces_every_discovered_slot_with_one_font(tmp_path, monkeypatch) -> None:
    root = tmp_path / "game"
    assets = root / "Assets"
    assets.mkdir(parents=True)
    build_pak(
        {
            "Libs/UI/one.gfx": b"one",
            "Libs/UI/two.gfx": b"two",
            "Libs/UI/none.gfx": b"none",
        },
        assets / "ui.pak",
    )
    font = tmp_path / "font.ttf"
    font.write_bytes(b"font")
    calls = []

    def fake_scan(source, _ffdec):
        return {
            b"one": (FontSlot(7, "One"),),
            b"two": (FontSlot(16, "Two"), FontSlot(17, "Two Bold")),
            b"none": (),
        }[source.read_bytes()]

    def fake_replace(source, destination, replacements, *, ffdec_cli=None):
        calls.append((source.read_bytes(), dict(replacements), ffdec_cli))
        destination.write_bytes(b"patched-" + source.read_bytes())
        return destination

    monkeypatch.setattr("cryengine_localization.core.batch_workflow.scan_gfx_fonts", fake_scan)
    monkeypatch.setattr("cryengine_localization.core.batch_workflow.replace_font_slots", fake_replace)
    output = tmp_path / "out" / "zzz_fonts.pak"

    report = build_batch_font_overlay(root, font, output, ffdec_cli="ffdec-cli.exe")

    assert report.replaced_paths == ("Libs/UI/one.gfx", "Libs/UI/two.gfx")
    assert report.skipped_paths == ("Libs/UI/none.gfx",)
    assert read_pak_members(output, report.replaced_paths) == {
        "Libs/UI/one.gfx": b"patched-one",
        "Libs/UI/two.gfx": b"patched-two",
    }
    assert calls == [
        (b"one", {7: font}, "ffdec-cli.exe"),
        (b"two", {16: font, 17: font}, "ffdec-cli.exe"),
    ]


def test_build_batch_font_overlay_reports_member_failure_without_output(tmp_path, monkeypatch) -> None:
    root = tmp_path / "game"
    assets = root / "Assets"
    assets.mkdir(parents=True)
    build_pak({"Libs/UI/bad.gfx": b"bad"}, assets / "ui.pak")
    font = tmp_path / "font.ttf"
    font.write_bytes(b"font")
    monkeypatch.setattr(
        "cryengine_localization.core.batch_workflow.scan_gfx_fonts",
        lambda *_args, **_kwargs: (FontSlot(7, "Bad"),),
    )
    monkeypatch.setattr(
        "cryengine_localization.core.batch_workflow.replace_font_slots",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(GfxToolError("replacement failed")),
    )
    output = tmp_path / "out.pak"

    with pytest.raises(GfxToolError, match=r"Assets/ui\.pak:Libs/UI/bad\.gfx"):
        build_batch_font_overlay(root, font, output, ffdec_cli="ffdec-cli.exe")

    assert not output.exists()


def test_build_batch_font_overlay_skips_no_slot_scan_errors(tmp_path, monkeypatch) -> None:
    root = tmp_path / "game"
    assets = root / "Assets"
    assets.mkdir(parents=True)
    build_pak({"Libs/UI/none.gfx": b"none", "Libs/UI/with-font.gfx": b"font"}, assets / "ui.pak")
    font = tmp_path / "font.ttf"
    font.write_bytes(b"font")

    def fake_scan(source, _ffdec):
        if source.read_bytes() == b"none":
            raise GfxNoFontSlotsError("FFDec output contained no DefineFont3 slots")
        return (FontSlot(7, "Body"),)

    monkeypatch.setattr("cryengine_localization.core.batch_workflow.scan_gfx_fonts", fake_scan)
    monkeypatch.setattr(
        "cryengine_localization.core.batch_workflow.replace_font_slots",
        lambda _source, destination, _replacements, **_kwargs: destination.write_bytes(b"patched"),
    )

    report = build_batch_font_overlay(root, font, tmp_path / "fonts.pak", ffdec_cli="ffdec")

    assert report.replaced_paths == ("Libs/UI/with-font.gfx",)
    assert report.skipped_paths == ("Libs/UI/none.gfx",)
