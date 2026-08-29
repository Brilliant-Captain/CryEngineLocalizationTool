from __future__ import annotations

import json
import hashlib
import zipfile

from cryengine_localization.cli.main import main
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
