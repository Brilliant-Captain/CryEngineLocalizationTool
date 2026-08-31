from __future__ import annotations

import json

import pytest

from cryengine_localization.core.apply import apply_catalog_to_json, apply_catalog_to_pak, plan_translation_changes
from cryengine_localization.adapters.pak import build_pak
from cryengine_localization.core.catalog import CatalogEntry


def test_apply_localizations_changes_only_values() -> None:
    data = {"Localizations": [{"key": "ui_start", "value": "Start"}, {"key": "ui_exit", "value": "Exit"}]}
    entries = [
        CatalogEntry("x.json:ui_start", "x.json", "ui_start", "Start", "hash", "开始"),
        CatalogEntry("x.json:ui_exit", "x.json", "ui_exit", "Exit", "hash", "退出"),
    ]

    output = apply_catalog_to_json(data, entries)

    assert output["Localizations"][0]["key"] == "ui_start"
    assert output["Localizations"][0]["value"] == "开始"
    assert data["Localizations"][0]["value"] == "Start"


def test_dry_run_skips_empty_and_stale_translations() -> None:
    entries = [
        CatalogEntry("x:a", "x.json", "a", "A", "hash", "译文"),
        CatalogEntry("x:b", "x.json", "b", "B", "hash", "", status="active"),
        CatalogEntry("x:c", "x.json", "c", "C", "hash", "旧", status="stale"),
    ]

    changes = plan_translation_changes(entries)

    assert [(change.text_key, change.translation) for change in changes] == [("a", "译文")]


def test_dry_run_skips_report_only_translations() -> None:
    entries = [
        CatalogEntry(
            "ui.gfx:raw@0x10",
            "ui.gfx",
            "raw@0x10",
            "Start",
            "hash",
            "开始",
            status="report-only",
        )
    ]

    assert plan_translation_changes(entries) == []


def test_apply_rejects_placeholder_loss() -> None:
    data = {"Localizations": [{"key": "x", "value": "Hello {name}"}]}
    entries = [CatalogEntry("x.json:x", "x.json", "x", "Hello {name}", "hash", "你好")]

    with pytest.raises(ValueError, match="placeholder"):
        apply_catalog_to_json(data, entries)


def test_apply_pak_rejects_in_place_output(tmp_path) -> None:
    pak = tmp_path / "source.pak"
    build_pak({"x.json": b'{"value":"x"}'}, pak)

    with pytest.raises(ValueError, match="differ"):
        apply_catalog_to_pak(str(pak), [], str(pak))


def test_apply_pak_rejects_stale_source_hash(tmp_path) -> None:
    pak = tmp_path / "source.pak"
    build_pak({"x.json": b'{"Localizations":[{"key":"x","value":"New"}]}'}, pak)
    entry = CatalogEntry("x.json:x", "x.json", "x", "Old", "old-hash", "译文")

    with pytest.raises(ValueError, match="source changed"):
        apply_catalog_to_pak(str(pak), [entry], str(tmp_path / "out.pak"))


def test_apply_pak_rejects_unsafe_or_unknown_source_path(tmp_path) -> None:
    pak = tmp_path / "source.pak"
    build_pak({"x.json": b'{"value":"x"}'}, pak)
    unsafe = CatalogEntry("../x.json:x", "../x.json", "x", "x", "hash", "译文")
    unknown = CatalogEntry("missing.json:x", "missing.json", "x", "x", "hash", "译文")

    with pytest.raises(ValueError, match="parent traversal"):
        apply_catalog_to_pak(str(pak), [unsafe], str(tmp_path / "unsafe.pak"))
    with pytest.raises(ValueError, match="absent from PAK"):
        apply_catalog_to_pak(str(pak), [unknown], str(tmp_path / "unknown.pak"))


def test_apply_duplicate_keys_matches_original_text_individually() -> None:
    data = {
        "Localizations": [
            {"key": "same", "value": "One"},
            {"key": "same", "value": "Two"},
        ]
    }
    entries = [
        CatalogEntry("x.json:same", "x.json", "same", "One", "hash-one", "一"),
        CatalogEntry("x.json:same", "x.json", "same", "Two", "hash-two", "二"),
    ]

    output = apply_catalog_to_json(data, entries)

    assert [item["value"] for item in output["Localizations"]] == ["一", "二"]
