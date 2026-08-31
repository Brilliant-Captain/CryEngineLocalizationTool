from __future__ import annotations

from pathlib import Path

from cryengine_localization.core.profile import BatchProfile, FontProfile, ProjectProfile
from cryengine_localization.gui_model import (
    build_catalog_export_args,
    build_cli_args,
    confirm_csv_overwrite,
    profile_from_form,
    profile_to_form,
)


def test_generic_build_args_do_not_inject_a_game_name() -> None:
    assert build_cli_args("source.pak", "translations.csv", "out.pak", "manifest.json", "zh-CN") == [
        "build",
        "source.pak",
        "translations.csv",
        "--output-pak",
        "out.pak",
        "--manifest",
        "manifest.json",
        "--language",
        "zh-CN",
        "--overlay-mode",
        "standalone",
    ]


def test_build_args_keep_explicit_generic_options() -> None:
    assert build_cli_args(
        "source.pak",
        "translations.csv",
        "out.pak",
        "manifest.json",
        "zh-CN",
        project="ExampleProject",
        overlay_mode="english-path-overlay",
        engine_version="5.6",
    )[-6:] == [
        "--overlay-mode",
        "english-path-overlay",
        "--engine-version",
        "5.6",
        "--project",
        "ExampleProject",
    ]


def test_catalog_export_args_use_selected_paths() -> None:
    assert build_catalog_export_args("source.pak", "work/translations.csv") == [
        "catalog",
        "export",
        "source.pak",
        "--output",
        "work/translations.csv",
    ]


def test_profile_form_round_trip_is_generic() -> None:
    profile = ProjectProfile(
        name="Example",
        engine_version="5.6",
        source_pak="source.pak",
        translation_csv="translations.csv",
        output_pak="out.pak",
        manifest="manifest.json",
        language="zh-CN",
        ui_language="en-US",
        overlay_mode="english-path-overlay",
    )

    form = profile_to_form(profile)
    assert profile_from_form(form) == profile
    assert "WarOfRights" not in str(form)


def test_csv_overwrite_requires_confirmation(tmp_path) -> None:
    output = tmp_path / "translations.csv"
    assert confirm_csv_overwrite(output, lambda _path: True)
    output.write_text("existing", encoding="utf-8")
    assert not confirm_csv_overwrite(output, lambda _path: False)
    assert confirm_csv_overwrite(output, lambda _path: True)


def test_profile_form_round_trip_preserves_subset_font_path() -> None:
    profile = ProjectProfile(
        name="Example",
        source_pak="source.pak",
        translation_csv="translations.csv",
        output_pak="out.pak",
        manifest="manifest.json",
        font=FontProfile(coverage_font="font.ttf", coverage_text="chars.txt", subset_output_font="subset.ttf"),
    )

    assert profile_from_form(profile_to_form(profile)) == profile


def test_profile_form_round_trip_preserves_batch_workflow_settings() -> None:
    profile = ProjectProfile(
        name="Batch",
        batch=BatchProfile(
            enabled=True,
            game_root="game",
            catalog_csv="work/all.csv",
            legacy_translation_csv="work/old.csv",
            scan_report="work/report.json",
            translation_overlay_pak="work/translation.pak",
            manifest="work/manifest.json",
            font_file="font.ttf",
            font_overlay_pak="work/fonts.pak",
            ffdec="ffdec-cli.exe",
        ),
    )

    form = profile_to_form(profile)

    assert form["batch_enabled"] == "true"
    assert form["batch_legacy_translation_csv"] == "work/old.csv"
    assert profile_from_form(form) == profile
