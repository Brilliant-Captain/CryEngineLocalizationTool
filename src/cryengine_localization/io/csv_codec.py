"""UTF-8 translation table codec."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, TextIO

from cryengine_localization.core.catalog import CatalogEntry


FIELDNAMES = (
    "resource_id",
    "source_path",
    "text_key",
    "original_text",
    "translation",
    "status",
    "original_hash",
)
REQUIRED_FIELDS = set(FIELDNAMES)


def _open_text(path_or_file: str | Path | TextIO, mode: str):
    if hasattr(path_or_file, "read") or hasattr(path_or_file, "write"):
        return path_or_file, False
    encoding = "utf-8-sig" if "r" in mode else "utf-8"
    return Path(path_or_file).open(mode, encoding=encoding, newline=""), True


def export_catalog(entries: Iterable[CatalogEntry], path_or_file: str | Path | TextIO) -> None:
    handle, should_close = _open_text(path_or_file, "w")
    try:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        for entry in entries:
            writer.writerow({field: getattr(entry, field) for field in FIELDNAMES})
    finally:
        if should_close:
            handle.close()


def import_catalog(path_or_file: str | Path | TextIO) -> list[CatalogEntry]:
    handle, should_close = _open_text(path_or_file, "r")
    try:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        missing = REQUIRED_FIELDS - fields
        if missing:
            raise ValueError(f"translation table missing columns: {', '.join(sorted(missing))}")
        entries: list[CatalogEntry] = []
        for row in reader:
            entries.append(
                CatalogEntry(
                    resource_id=row["resource_id"],
                    source_path=row["source_path"],
                    text_key=row["text_key"],
                    original_text=row["original_text"],
                    original_hash=row["original_hash"],
                    translation=row.get("translation", ""),
                    status=row.get("status", "active"),
                )
            )
        return entries
    finally:
        if should_close:
            handle.close()
