from __future__ import annotations

from cryengine_localization.adapters.cryengine import identify_project


def test_identify_cryengine_project_by_cryproject_assets_and_paks(tmp_path) -> None:
    (tmp_path / "game.cryproject").write_text(
        '{"info":{"name":"fixture"},"require":{"engine_version":"5.7.1"}}',
        encoding="utf-8",
    )
    (tmp_path / "Assets").mkdir()
    (tmp_path / "Assets" / "GameData.pak").write_bytes(b"fixture")

    info = identify_project(tmp_path)

    assert info.engine == "CryEngine"
    assert info.confidence >= 0.8
    assert info.has_cryproject is True
    assert info.has_assets is True
    assert info.engine_version == "5.7.1"
    assert info.engine_version_source == ".cryproject"
    assert info.engine_generation_hint == "CryEngine 5"


def test_identify_localization_only_cryengine_resource_set(tmp_path) -> None:
    localization = tmp_path / "localization"
    localization.mkdir()
    (localization / "english_xml.pak").write_bytes(b"fixture")
    (localization / "HUD_Font_LocFont.gfx").write_bytes(b"GFX fixture")

    info = identify_project(tmp_path)

    assert info.engine == "CryEngine"
    assert info.confidence > 0
    assert info.pak_files == (localization / "english_xml.pak",)
    assert info.engine_version is None
    assert info.engine_version_source is None
    assert info.engine_generation_hint == "CryEngine 2/3-era"


def test_identify_engine_version_from_crysystem_dll(tmp_path, monkeypatch) -> None:
    binary = tmp_path / "Bin64" / "CrySystem.dll"
    binary.parent.mkdir()
    binary.write_bytes(b"fixture")
    monkeypatch.setattr(
        "cryengine_localization.adapters.cryengine._windows_file_version",
        lambda path: "3.8.6.0" if path == binary else None,
    )

    info = identify_project(tmp_path)

    assert info.engine == "CryEngine"
    assert info.engine_version == "3.8.6.0"
    assert info.engine_version_source == "Bin64/CrySystem.dll"
    assert info.engine_generation_hint == "CryEngine 3"
