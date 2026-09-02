from __future__ import annotations

import csv
from io import StringIO

import pytest

from cryengine_localization.core.catalog import CatalogEntry
from cryengine_localization.io.csv_codec import export_catalog, export_friendly_catalog, import_catalog
from cryengine_localization.core.translation_table import merge_translations


def _entry() -> CatalogEntry:
    return CatalogEntry(
        resource_id="x.json:key",
        source_path="x.json",
        text_key="key",
        original_text='line1\nline2, "quoted" <b>x</b> {name}',
        original_hash="hash",
    )


def test_csv_roundtrip_preserves_edge_text_and_utf8(tmp_path) -> None:
    path = tmp_path / "translations.csv"
    original = [_entry()]

    export_catalog(original, path)
    loaded = import_catalog(path)

    assert loaded == original
    assert "你好" not in path.read_text(encoding="utf-8")


def test_csv_places_translation_next_to_original_and_hash_last() -> None:
    output = StringIO()

    export_catalog([_entry()], output)
    header = next(csv.reader(StringIO(output.getvalue())))

    assert header == [
        "resource_id",
        "source_path",
        "text_key",
        "original_text",
        "translation",
        "status",
        "original_hash",
        "source_archive",
    ]


def test_import_accepts_previous_column_order() -> None:
    source = StringIO(
        "resource_id,source_path,text_key,original_text,original_hash,translation,status\n"
        "x.json:key,x.json,key,Original,hash,Translation,active\n"
    )

    assert import_catalog(source) == [
        CatalogEntry("x.json:key", "x.json", "key", "Original", "hash", "Translation", "active")
    ]


def test_csv_roundtrip_preserves_optional_source_archive(tmp_path) -> None:
    path = tmp_path / "translations.csv"
    original = [
        CatalogEntry(
            "x.json:key",
            "x.json",
            "key",
            "Original",
            "hash",
            source_archive="Assets/GameData.pak",
        )
    ]

    export_catalog(original, path)

    assert import_catalog(path) == original


def test_import_changes_translation_only() -> None:
    source = [_entry()]
    rows = [dict(_entry().__dict__, translation="你好")]

    merged = merge_translations(source, rows)

    assert merged[0].translation == "你好"
    assert merged[0].original_text == source[0].original_text
    assert merged[0].original_hash == source[0].original_hash


def test_import_rejects_changed_original_columns() -> None:
    source = [_entry()]
    row = dict(_entry().__dict__, original_text="tampered", translation="译文")

    with pytest.raises(ValueError, match="original_text"):
        merge_translations(source, [row])


def test_friendly_catalog_uses_existing_translation_as_source_and_imports_target(tmp_path) -> None:
    entry = CatalogEntry(
        "x.xml:key",
        "x.xml",
        "key",
        "原始草稿",
        "hash",
        "Existing English",
    )
    path = tmp_path / "friendly.csv"
    export_friendly_catalog([entry], path)
    text = path.read_text(encoding="utf-8")
    assert "source_text" in text and "target_translation" in text
    assert "Existing English" in text

    text = text.replace(
        "Existing English,,原始草稿",
        "Existing English,中文译文,原始草稿",
    )
    path.write_text(text, encoding="utf-8-sig")
    loaded = import_catalog(path)
    assert loaded[0].translation == "中文译文"
    assert loaded[0].original_text == "原始草稿"
