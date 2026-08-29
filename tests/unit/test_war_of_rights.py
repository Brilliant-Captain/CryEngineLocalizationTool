from __future__ import annotations

import pytest

from cryengine_localization.adapters.war_of_rights import (
    DuplicateEnglishPathError,
    backup_file,
    preview_language_config,
    reject_duplicate_english_overlay,
    restore_backup,
)


def test_language_config_preview_updates_existing_keys_and_reports_diff() -> None:
    before = "g_language=french\nLocalization.Language=french\n"

    preview = preview_language_config(before, "english")

    assert "g_language=english" in preview.after
    assert "Localization.Language=english" in preview.after
    assert any(line.startswith("-") for line in preview.diff)


def test_language_config_preview_adds_missing_keys() -> None:
    preview = preview_language_config("-- config\n", "english")

    assert "g_language=english" in preview.after
    assert "Localization.Language=english" in preview.after


def test_duplicate_english_overlay_is_rejected_case_insensitively() -> None:
    with pytest.raises(DuplicateEnglishPathError):
        reject_duplicate_english_overlay(
            ["Localization/english/MainMenu.json"],
            ["localization/ENGLISH/mainmenu.json"],
        )


def test_backup_and_restore_verify_hash(tmp_path) -> None:
    source = tmp_path / "autoexec.cfg"
    source.write_text("g_language=english\n", encoding="utf-8")
    record = backup_file(source, tmp_path / "backup")
    source.write_text("g_language=french\n", encoding="utf-8")

    restore_backup(record)

    assert source.read_text(encoding="utf-8") == "g_language=english\n"
