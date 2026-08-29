"""Validation and merge operations for source-preserving translation tables."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Mapping

from cryengine_localization.core.catalog import CatalogEntry


_SOURCE_FIELDS = ("resource_id", "source_path", "text_key", "original_text", "original_hash")


def merge_translations(
    source_entries: Iterable[CatalogEntry], imported_rows: Iterable[Mapping[str, str] | CatalogEntry]
) -> list[CatalogEntry]:
    """Apply only translation values after byte-stable source-field checks."""

    source = list(source_entries)
    by_id = {entry.resource_id: entry for entry in source}
    if len(by_id) != len(source):
        raise ValueError("source catalog contains duplicate resource_id values")
    seen: set[str] = set()
    result: list[CatalogEntry] = []
    for row in imported_rows:
        values = row.__dict__ if isinstance(row, CatalogEntry) else row
        resource_id = values.get("resource_id", "")
        if resource_id in seen:
            raise ValueError(f"duplicate translation resource_id: {resource_id}")
        seen.add(resource_id)
        original = by_id.get(resource_id)
        if original is None:
            raise ValueError(f"unknown resource_id: {resource_id}")
        for field in _SOURCE_FIELDS:
            if values.get(field) != getattr(original, field):
                raise ValueError(f"{field} is read-only for {resource_id}")
        result.append(replace(original, translation=values.get("translation", "")))
    return result

