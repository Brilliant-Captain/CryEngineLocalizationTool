from __future__ import annotations

import json
from dataclasses import replace

import pytest

from cryengine_localization.core.profile import (
    BatchProfile,
    ProfileError,
    ProjectProfile,
    load_profile,
    save_profile,
)


def test_profile_round_trip_preserves_generic_settings(tmp_path) -> None:
    path = tmp_path / "project.json"
    profile = ProjectProfile(
        name="Example CryEngine Project",
        engine_version="5.6",
        source_pak="D:/Game/Assets/GameData.pak",
        translation_csv="work/translations.csv",
        output_pak="work/translation_overlay.pak",
        manifest="work/manifest.json",
        language="zh-CN",
        ui_language="zh-CN",
        overlay_mode="english-path-overlay",
    )

    assert save_profile(profile, path) == path.resolve()
    loaded = load_profile(path)

    assert loaded == profile
    assert "WarOfRights" not in path.read_text(encoding="utf-8")


def test_profile_validation_requires_core_paths_and_supported_values() -> None:
    profile = ProjectProfile(name="Generic")

    with pytest.raises(ProfileError, match="source_pak"):
        profile.validate()

    valid = ProjectProfile(
        name="Generic",
        source_pak="source.pak",
        translation_csv="translations.csv",
        output_pak="output.pak",
        manifest="manifest.json",
        language="zh-CN",
        overlay_mode="standalone",
    )
    assert valid.validate() == valid

    with pytest.raises(ProfileError, match="overlay_mode"):
        replace(valid, overlay_mode="game-specific").validate()


def test_profile_rejects_unknown_fields(tmp_path) -> None:
    path = tmp_path / "invalid.json"
    data = ProjectProfile(
        name="Generic",
        source_pak="source.pak",
        translation_csv="translations.csv",
        output_pak="output.pak",
        manifest="manifest.json",
    ).to_dict()
    data["unexpected"] = True
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ProfileError, match="unexpected"):
        load_profile(path)


def test_profile_defaults_do_not_assume_a_game_process() -> None:
    profile = ProjectProfile(
        name="Generic",
        source_pak="source.pak",
        translation_csv="translations.csv",
        output_pak="output.pak",
        manifest="manifest.json",
    )

    assert profile.install.process_names == ()


def test_old_profile_without_ui_language_defaults_to_chinese(tmp_path) -> None:
    path = tmp_path / "old.json"
    data = ProjectProfile(
        name="Generic",
        source_pak="source.pak",
        translation_csv="translations.csv",
        output_pak="output.pak",
        manifest="manifest.json",
    ).to_dict()
    data.pop("ui_language")
    path.write_text(json.dumps(data), encoding="utf-8")

    assert load_profile(path).ui_language == "zh-CN"


def test_batch_profile_round_trip_does_not_require_legacy_single_pak_paths(tmp_path) -> None:
    path = tmp_path / "batch.json"
    profile = ProjectProfile(
        name="Batch Project",
        manifest="",
        batch=BatchProfile(
            enabled=True,
            game_root="D:/Games/Example",
            catalog_csv="work/all-text.csv",
            scan_report="work/scan-report.json",
            translation_overlay_pak="work/zzz_translation.pak",
            manifest="work/manifest.json",
            font_file="C:/Fonts/NotoSansCJK.ttf",
            font_overlay_pak="work/zzz_fonts.pak",
            ffdec="C:/Tools/ffdec-cli.exe",
            legacy_translation_csv="work/previous-translations.csv",
        ),
    )

    assert save_profile(profile, path) == path.resolve()
    assert load_profile(path) == profile
    assert load_profile(path).batch.enabled is True
