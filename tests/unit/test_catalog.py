from __future__ import annotations

import hashlib

import pytest

from cryengine_localization.core.catalog import catalog_from_json
from cryengine_localization.io.json_localization import parse_json_relaxed


def test_parse_war_of_rights_trailing_comma_and_extract_key_value_records() -> None:
    raw = b'{\n  "Localizations": [\n    {"key": "ui_start", "value": "Start, now"},\n  ]\n}'

    parsed = parse_json_relaxed(raw)
    entries = catalog_from_json("Localization/english/MainMenu.json", parsed)

    assert len(entries) == 1
    assert entries[0].resource_id.endswith(":ui_start")
    assert entries[0].original_text == "Start, now"
    assert entries[0].original_hash == hashlib.sha256(b"Start, now").hexdigest()


def test_nested_json_strings_are_extractable() -> None:
    entries = catalog_from_json("nested.json", {"menu": {"title": "Hello"}, "items": ["One"]})

    assert {entry.text_key for entry in entries} == {"menu.title", "items[0]"}

