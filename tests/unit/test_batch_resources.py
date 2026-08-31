from __future__ import annotations

from cryengine_localization.adapters.batch_resources import scan_game_resources
from cryengine_localization.adapters.pak import build_pak


SPREADSHEET = b'''<?xml version="1.0"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="Strings"><Table>
  <Row><Cell><Data ss:Type="String">KEY</Data></Cell><Cell><Data ss:Type="String">ORIGINAL TEXT</Data></Cell><Cell><Data ss:Type="String">TRANSLATED TEXT</Data></Cell></Row>
  <Row><Cell><Data ss:Type="String">ui_exit</Data></Cell><Cell><Data ss:Type="String">Exit</Data></Cell><Cell><Data ss:Type="String"></Data></Cell></Row>
 </Table></Worksheet>
</Workbook>'''


def test_scan_game_resources_collects_writable_rows_and_report_only_gfx(tmp_path) -> None:
    root = tmp_path / "game"
    assets = root / "Assets"
    assets.mkdir(parents=True)
    build_pak(
        {
            "Localization/english/MainMenu.json": b'{"Localizations":[{"key":"ui_start","value":"Start"}]}',
            "Localization/english/Menu.xml": SPREADSHEET,
        },
        assets / "a.pak",
    )
    build_pak(
        {"Libs/UI/MainMenu.gfx": b"GFX\x08\x00\x00\x00\x00Main Menu\x00"},
        assets / "ui.pak",
    )

    result = scan_game_resources(root)

    assert {(entry.source_path, entry.text_key, entry.source_archive) for entry in result.catalog if entry.status == "active"} == {
        ("Localization/english/MainMenu.json", "ui_start", "Assets/a.pak"),
        ("Localization/english/Menu.xml", "ui_exit", "Assets/a.pak"),
    }
    assert any(
        entry.status == "report-only"
        and entry.source_path == "Libs/UI/MainMenu.gfx"
        and entry.source_archive == "Assets/ui.pak"
        and entry.original_text == "Main Menu"
        for entry in result.catalog
    )
    assert result.report.gfx_candidates[0].archive_path == "Assets/ui.pak"
    assert result.report.gfx_candidates[0].resource_path == "Libs/UI/MainMenu.gfx"


def test_scan_game_resources_records_bad_content_and_keeps_scanning(tmp_path) -> None:
    root = tmp_path / "game"
    assets = root / "Assets"
    assets.mkdir(parents=True)
    build_pak(
        {
            "bad.json": b"{broken",
            "bad.xml": b"<broken",
            "good.json": b'{"title":"Good"}',
        },
        assets / "source.pak",
    )

    result = scan_game_resources(root)

    assert [(entry.source_path, entry.original_text) for entry in result.catalog] == [("good.json", "Good")]
    assert {(issue.resource_path, issue.kind) for issue in result.report.issues} == {
        ("bad.json", "json"),
        ("bad.xml", "xml"),
    }


def test_scan_game_resources_keeps_loose_files_distinct_from_pak_members(tmp_path) -> None:
    root = tmp_path / "game"
    assets = root / "Assets"
    assets.mkdir(parents=True)
    build_pak({"same.json": b'{"title":"Packed"}'}, assets / "source.pak")
    (root / "same.json").write_bytes(b'{"title":"Loose"}')

    result = scan_game_resources(root)

    entries = [entry for entry in result.catalog if entry.source_path == "same.json"]
    assert {(entry.original_text, entry.source_archive) for entry in entries} == {
        ("Packed", "Assets/source.pak"),
        ("Loose", "[loose]"),
    }
    assert len({entry.resource_id for entry in entries}) == 2


def test_scan_game_resources_marks_non_localization_and_malformed_json_as_report_only(tmp_path) -> None:
    root = tmp_path / "game"
    assets = root / "Assets"
    assets.mkdir(parents=True)
    build_pak(
        {
            "Scripts/Definition.json": b'{"Name":"Unsafe to rewrite"}',
            "Localization/english/Broken.json": b'{"Localizations":[{"key":"ui_start","value":"Start" "next":"still visible"}]}',
        },
        assets / "source.pak",
    )

    result = scan_game_resources(root)

    script_row = next(item for item in result.catalog if item.original_text == "Unsafe to rewrite")
    broken_row = next(item for item in result.catalog if item.original_text == "Start")
    assert script_row.status == "report-only"
    assert broken_row.status == "report-only"
    assert any(issue.resource_path == "Localization/english/Broken.json" for issue in result.report.issues)
