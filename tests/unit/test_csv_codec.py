from __future__ import annotations

import csv
from io import StringIO

import pytest

from cryengine_localization.core.catalog import CatalogEntry
from cryengine_localization.io.csv_codec import export_catalog, import_catalog
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

