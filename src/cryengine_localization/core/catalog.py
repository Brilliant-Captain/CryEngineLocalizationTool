"""Source-preserving localization catalog models and extraction."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Any, Iterable


@dataclass(frozen=True)
class CatalogEntry:
    resource_id: str
    source_path: str
    text_key: str
    original_text: str
    original_hash: str
    translation: str = ""
    status: str = "active"


def _entry(source_path: str, text_key: str, text: str) -> CatalogEntry:
    return CatalogEntry(
        resource_id=f"{source_path}:{text_key}",
        source_path=source_path,
        text_key=text_key,
        original_text=text,
        original_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def _walk_strings(value: Any, path: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from _walk_strings(child, child_path)
    elif isinstance(value, list):
        # CryEngine localization files conventionally use key/value records.
        if all(isinstance(item, dict) and "key" in item and "value" in item for item in value):
            for item in value:
                key = item["key"]
                text = item["value"]
                if isinstance(key, str) and isinstance(text, str):
                    yield key, text
            return
        for index, child in enumerate(value):
            yield from _walk_strings(child, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def catalog_from_json(source_path: str, data: Any) -> list[CatalogEntry]:
    """Extract text leaves while keeping source path and stable keys."""

    leaves = [(key, text) for key, text in _walk_strings(data) if key]
    counts: dict[str, int] = {}
    for key, _text in leaves:
        counts[key] = counts.get(key, 0) + 1
    seen: dict[str, int] = {}
    entries: list[CatalogEntry] = []
    for key, text in leaves:
        seen[key] = seen.get(key, 0) + 1
        resource_id = f"{source_path}:{key}"
        if counts[key] > 1:
            resource_id += f"#{seen[key]}"
        entries.append(
            CatalogEntry(
                resource_id=resource_id,
                source_path=source_path,
                text_key=key,
                original_text=text,
                original_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
    return entries


def catalog_from_json_bytes(source_path: str, raw: bytes) -> list[CatalogEntry]:
    from cryengine_localization.io.json_localization import parse_json_relaxed

    return catalog_from_json(source_path, parse_json_relaxed(raw))


def with_translation(entry: CatalogEntry, translation: str) -> CatalogEntry:
    return replace(entry, translation=translation)
