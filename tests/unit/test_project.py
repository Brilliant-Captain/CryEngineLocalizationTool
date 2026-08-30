from __future__ import annotations

from cryengine_localization.adapters.cryengine import identify_project


def test_identify_cryengine_project_by_cryproject_assets_and_paks(tmp_path) -> None:
    (tmp_path / "game.cryproject").write_text("{\"info\": {\"name\": \"fixture\"}}", encoding="utf-8")
    (tmp_path / "Assets").mkdir()
    (tmp_path / "Assets" / "GameData.pak").write_bytes(b"fixture")

    info = identify_project(tmp_path)

    assert info.engine == "CryEngine"
    assert info.confidence >= 0.8
    assert info.has_cryproject is True
    assert info.has_assets is True


def test_identify_localization_only_cryengine_resource_set(tmp_path) -> None:
    localization = tmp_path / "localization"
    localization.mkdir()
    (localization / "english_xml.pak").write_bytes(b"fixture")
    (localization / "HUD_Font_LocFont.gfx").write_bytes(b"GFX fixture")

    info = identify_project(tmp_path)

    assert info.engine == "CryEngine"
    assert info.confidence > 0
    assert info.pak_files == (localization / "english_xml.pak",)
