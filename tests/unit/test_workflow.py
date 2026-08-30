from __future__ import annotations

import csv
import json
import zipfile

from cryengine_localization.cli.main import main
from cryengine_localization.core.profile import ProjectProfile, save_profile
from cryengine_localization.core.workflow import catalog_from_pak
from cryengine_localization.io.spreadsheetml import catalog_from_spreadsheetml_bytes

from tests.unit.test_spreadsheetml import SPREADSHEET


def _source_pak(tmp_path):
    source = tmp_path / "Assets" / "source.pak"
    source.parent.mkdir()
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(
            "Localization/english/MainMenu.json",
            '{"Localizations":[{"key":"ui_start","value":"Start"},]}',
        )
    return source


def _profile(tmp_path, source, csv_path=None):
    return ProjectProfile(
        name="Generic CryEngine Project",
        engine_version="5.6",
        source_pak=str(source),
        translation_csv=str(csv_path or tmp_path / "translations.csv"),
        output_pak=str(tmp_path / "out.pak"),
        manifest=str(tmp_path / "manifest.json"),
        language="zh-CN",
        overlay_mode="english-path-overlay",
    )


def test_profile_init_writes_a_generic_template(tmp_path, capsys) -> None:
    path = tmp_path / "project.json"

    assert main(["profile", "init", "--output", str(path)]) == 0
    capsys.readouterr()
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["schema_version"] == 1
    assert data["name"] == ""
    assert "WarOfRights" not in path.read_text(encoding="utf-8")
    assert main(["profile", "validate", str(path)]) == 2
    assert "name" in capsys.readouterr().err


def test_workflow_export_refuses_existing_csv_without_overwrite(tmp_path, capsys) -> None:
    source = _source_pak(tmp_path)
    csv_path = tmp_path / "translations.csv"
    csv_path.write_text("keep", encoding="utf-8")
    profile_path = tmp_path / "project.json"
    save_profile(_profile(tmp_path, source, csv_path), profile_path)

    assert main(["workflow", "export-csv", str(profile_path)]) == 2
    assert csv_path.read_text(encoding="utf-8") == "keep"
    assert "overwrite" in capsys.readouterr().err.lower()

    assert main(["workflow", "export-csv", str(profile_path), "--overwrite"]) == 0
    output = capsys.readouterr().out
    assert "exported 1 rows" in output
    assert "ui_start" in csv_path.read_text(encoding="utf-8")


def test_workflow_dry_run_and_build_use_profile_paths(tmp_path, capsys) -> None:
    source = _source_pak(tmp_path)
    csv_path = tmp_path / "translations.csv"
    profile_path = tmp_path / "project.json"
    save_profile(_profile(tmp_path, source, csv_path), profile_path)

    assert main(["workflow", "export-csv", str(profile_path)]) == 0
    capsys.readouterr()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    rows[0]["translation"] = "开始"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    assert main(["workflow", "dry-run", str(profile_path)]) == 0
    assert "开始" in capsys.readouterr().out

    assert main(["workflow", "build", str(profile_path)]) == 0
    output = capsys.readouterr().out
    assert "manifest" in output
    assert (tmp_path / "out.pak").is_file()
    assert (tmp_path / "manifest.json").is_file()


def test_catalog_and_build_support_spreadsheetml_pak(tmp_path) -> None:
    source = tmp_path / "source.pak"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("english_xml/text_ui_menus.xml", SPREADSHEET)
    raw = bytearray(source.read_bytes())
    local_name = b"english_xml\\text_ui_menus.xml"
    raw[30 : 30 + len(local_name)] = local_name
    source.write_bytes(raw)

    entries = catalog_from_pak(source)
    translated = [
        entry.__class__(
            entry.resource_id,
            entry.source_path,
            entry.text_key,
            entry.original_text,
            entry.original_hash,
            "\u5f00\u59cb" if entry.text_key == "ui_start" else entry.translation,
            entry.status,
        )
        for entry in entries
    ]

    from cryengine_localization.core.apply import apply_catalog_to_pak
    from cryengine_localization.adapters.pak import read_entry

    output = tmp_path / "output.pak"
    apply_catalog_to_pak(str(source), translated, str(output))
    output_entries = catalog_from_spreadsheetml_bytes(
        "english_xml/text_ui_menus.xml",
        read_entry(output, "english_xml/text_ui_menus.xml"),
    )

    assert next(item for item in output_entries if item.text_key == "ui_start").translation == "\u5f00\u59cb"
