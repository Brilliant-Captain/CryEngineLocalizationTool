from __future__ import annotations

import json
import hashlib
import zipfile

from cryengine_localization.cli.main import main
from cryengine_localization.adapters.swf import SWF_HEADER_SIZE, build_tag
from cryengine_localization.core.catalog import CatalogEntry
from cryengine_localization.io.csv_codec import export_catalog


def test_cli_identify_and_catalog_export(tmp_path, capsys) -> None:
    (tmp_path / "fixture.cryproject").write_text("{}", encoding="utf-8")
    (tmp_path / "Assets").mkdir()
    pak = tmp_path / "Assets" / "fixture.pak"
    with zipfile.ZipFile(pak, "w") as archive:
        archive.writestr(
            "Localization/english/MainMenu.json",
            '{"Localizations":[{"key":"ui_start","value":"Start"},]}',
        )

    assert main(["identify", str(tmp_path)]) == 0
    identified = json.loads(capsys.readouterr().out)
    assert identified["engine"] == "CryEngine"

    csv_path = tmp_path / "translations.csv"
    assert main(["catalog", "export", str(pak), "--output", str(csv_path)]) == 0
    assert "ui_start" in csv_path.read_text(encoding="utf-8")


def test_cli_build_writes_manifest_without_absolute_source_path(tmp_path, capsys) -> None:
    source = tmp_path / "Assets" / "fixture.pak"
    source.parent.mkdir()
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(
            "Localization/english/MainMenu.json",
            '{"Localizations":[{"key":"ui_start","value":"Start"},]}',
        )
    csv_path = tmp_path / "translations.csv"
    export_catalog(
        [CatalogEntry("Localization/english/MainMenu.json:ui_start", "Localization/english/MainMenu.json", "ui_start", "Start", hashlib.sha256(b"Start").hexdigest(), "开始")],
        csv_path,
    )
    output = tmp_path / "out.pak"
    manifest = tmp_path / "manifest.json"

    assert main(
        [
            "build",
            str(source),
            str(csv_path),
            "--output-pak",
            str(output),
            "--manifest",
            str(manifest),
            "--language",
            "zh-CN",
        ]
    ) == 0
    capsys.readouterr()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert output.is_file()
    assert data["target_language"] == "zh-CN"
    assert str(tmp_path) not in manifest.read_text(encoding="utf-8")
    with zipfile.ZipFile(output) as archive:
        assert "开始".encode("utf-8") in archive.read("Localization/english/MainMenu.json")


def test_cli_install_dry_run_does_not_write_game_root(tmp_path, capsys) -> None:
    game = tmp_path / "game"
    game.mkdir()
    source = tmp_path / "patch.pak"
    source.write_bytes(b"patch")
    record = tmp_path / "install.json"

    assert main(
        [
            "install",
            "--game-root",
            str(game),
            "--backup-dir",
            str(tmp_path / "backup"),
            "--record",
            str(record),
            "--file",
            f"{source}=Assets/patch.pak",
            "--dry-run",
        ]
    ) == 0
    capsys.readouterr()
    assert not (game / "Assets" / "patch.pak").exists()
    assert not record.exists()


def test_cli_apply_english_only_filters_non_english_rows(tmp_path, capsys) -> None:
    csv_path = tmp_path / "translations.csv"
    export_catalog(
        [
            CatalogEntry("Localization/english/MainMenu.json:x", "Localization/english/MainMenu.json", "x", "X", __import__('hashlib').sha256(b"X").hexdigest(), "中文"),
            CatalogEntry("Localization/Finnish/MainMenu.json:y", "Localization/Finnish/MainMenu.json", "y", "Y", __import__('hashlib').sha256(b"Y").hexdigest(), "芬兰语"),
        ],
        csv_path,
    )

    assert main(["apply", str(csv_path), "--dry-run", "--english-only"]) == 0
    output = capsys.readouterr().out
    assert "Localization/english/MainMenu.json" in output
    assert "Localization/Finnish/MainMenu.json" not in output


def test_cli_gui_passes_interface_language(monkeypatch) -> None:
    received: dict[str, str | None] = {}
    monkeypatch.setattr(
        "cryengine_localization.gui.launch_gui",
        lambda *, ui_language=None: received.setdefault("ui_language", ui_language),
    )

    assert main(["gui", "--ui-language", "en-US"]) == 0
    assert received["ui_language"] == "en-US"


def _gfx_fixture(font_marker: bytes = b"old", shape: bytes = b"shape") -> bytes:
    payload = (
        bytes(range(SWF_HEADER_SIZE))
        + build_tag(9, shape)
        + build_tag(75, (1).to_bytes(2, "little") + font_marker)
        + build_tag(0, b"")
    )
    return b"GFX\x08" + (8 + len(payload)).to_bytes(4, "little") + payload


def test_cli_font_assess_outputs_risk_report(tmp_path, capsys) -> None:
    gfx = tmp_path / "fixture.gfx"
    gfx.write_bytes(_gfx_fixture())

    assert main(["font", "assess", str(gfx)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["container"] == "GFX"
    assert report["font_tag_count"] == 1
    assert report["level"] in {"safe", "caution"}


def test_cli_font_migrate_writes_output(tmp_path, capsys) -> None:
    original = tmp_path / "original.gfx"
    candidate = tmp_path / "candidate.gfx"
    output = tmp_path / "migrated.gfx"
    original.write_bytes(_gfx_fixture())
    candidate.write_bytes(_gfx_fixture(b"new"))

    assert main(
        [
            "font",
            "migrate",
            str(original),
            "--candidate",
            str(candidate),
            "--output-gfx",
            str(output),
            "--slot",
            "1=placeholder.ttf",
        ]
    ) == 0
    capsys.readouterr()
    assert output.read_bytes() != original.read_bytes()
    assert output.read_bytes() == candidate.read_bytes()
