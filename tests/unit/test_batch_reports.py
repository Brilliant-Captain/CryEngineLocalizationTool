from __future__ import annotations

import csv

from cryengine_localization.core.catalog import CatalogEntry
from cryengine_localization.core.workflow import write_report_only_shards


def _entry(number: int, path: str) -> CatalogEntry:
    return CatalogEntry(
        resource_id=f"Assets/source.pak::{path}:raw@0x{number:08X}",
        source_path=path,
        text_key=f"raw@0x{number:08X}",
        original_text=f"text {number}",
        original_hash=str(number),
        status="report-only",
        source_archive="Assets/source.pak",
    )


def test_report_only_shards_group_by_resource_type_and_cap_rows(tmp_path) -> None:
    entries = [
        *(_entry(number, "Scripts/item.json") for number in range(5)),
        *(_entry(number, "Libs/UI/Menu.gfx") for number in range(5, 8)),
        _entry(8, "Definitions/item.xml"),
    ]

    index_path, index = write_report_only_shards(entries, tmp_path / "parts", rows_per_file=2)

    assert index_path == tmp_path / "parts" / "report-index.csv"
    assert [(item.resource_type, item.row_count) for item in index] == [
        ("gfx", 3),
        ("json", 5),
        ("xml", 1),
    ]
    with index_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["resource_type"] for row in rows} == {"gfx", "json", "xml"}
    for row in rows:
        with (tmp_path / "parts" / row["file"]).open("r", encoding="utf-8-sig", newline="") as handle:
            assert len(list(csv.DictReader(handle))) <= 2
