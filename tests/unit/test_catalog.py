from __future__ import annotations

import hashlib

import pytest

from cryengine_localization.core.catalog import CatalogEntry, catalog_from_json
from cryengine_localization.io.json_localization import parse_json_relaxed


def test_parse_war_of_rights_trailing_comma_and_extract_key_value_records() -> None:
    raw = b'{\n  "Localizations": [\n    {"key": "ui_start", "value": "Start, now"},\n  ]\n}'

    parsed = parse_json_relaxed(raw)
    entries = catalog_from_json("Localization/english/MainMenu.json", parsed)

    assert len(entries) == 1
    assert entries[0].resource_id.endswith(":ui_start")
    assert entries[0].original_text == "Start, now"
    assert entries[0].original_hash == hashlib.sha256(b"Start, now").hexdigest()


def test_parse_war_of_rights_missing_separator_between_localization_records() -> None:
    raw = (
        b'{"Localizations":['
        b'{"key":"ui_start","value":"Start }{ unchanged"}'
        b'{"key":"ui_exit","value":"Exit"},'
        b']}'
    )

    parsed = parse_json_relaxed(raw)
    entries = catalog_from_json("Localization/english/MainMenu.json", parsed)

    assert [(entry.text_key, entry.original_text) for entry in entries] == [
        ("ui_start", "Start }{ unchanged"),
        ("ui_exit", "Exit"),
    ]


def test_nested_json_strings_are_extractable() -> None:
    entries = catalog_from_json("nested.json", {"menu": {"title": "Hello"}, "items": ["One"]})

    assert {entry.text_key for entry in entries} == {"menu.title", "items[0]"}


def test_duplicate_localization_keys_get_stable_resource_ids() -> None:
    entries = catalog_from_json(
        "bindings.json",
        {"Localizations": [{"key": "same", "value": "One"}, {"key": "same", "value": "Two"}]},
    )

    assert [entry.resource_id for entry in entries] == [
        "bindings.json:same#1",
        "bindings.json:same#2",
    ]


def test_catalog_entry_accepts_optional_source_archive() -> None:
    entry = CatalogEntry(
        "MainMenu.json:ui_start",
        "MainMenu.json",
        "ui_start",
        "Start",
        "hash",
        source_archive="Assets/GameData.pak",
    )

    assert entry.source_archive == "Assets/GameData.pak"
