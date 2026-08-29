"""Translation application and dry-run planning."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from cryengine_localization.core.catalog import CatalogEntry
from cryengine_localization.core.stale import validate_translation


@dataclass(frozen=True)
class TranslationChange:
    source_path: str
    text_key: str
    original_text: str
    translation: str
    status: str


def plan_translation_changes(entries: Iterable[CatalogEntry]) -> list[TranslationChange]:
    changes: list[TranslationChange] = []
    for entry in entries:
        if not entry.translation or entry.status in {"stale", "orphaned", "invalid"}:
            continue
        validate_translation(entry.original_text, entry.translation)
        changes.append(
            TranslationChange(
                source_path=entry.source_path,
                text_key=entry.text_key,
                original_text=entry.original_text,
                translation=entry.translation,
                status=entry.status,
            )
        )
    return changes


def _set_path(root: Any, text_key: str, value: str) -> bool:
    """Set a dotted/indexed path emitted by the generic catalog walker."""

    import re

    tokens = re.findall(r"[^.\[\]]+|\[(\d+)\]", text_key)
    normalized = [int(token[0]) if token[0] else token for token in tokens]
    if not normalized:
        return False
    target = root
    for token in normalized[:-1]:
        try:
            target = target[token]
        except (KeyError, IndexError, TypeError):
            return False
    try:
        target[normalized[-1]] = value
    except (KeyError, IndexError, TypeError):
        return False
    return True


def apply_catalog_to_json(data: Any, entries: Iterable[CatalogEntry]) -> Any:
    """Return a deep-copied JSON object with safe translations applied."""

    output = copy.deepcopy(data)
    changes = plan_translation_changes(entries)
    if isinstance(output, dict) and isinstance(output.get("Localizations"), list):
        by_key = {change.text_key: change for change in changes}
        for item in output["Localizations"]:
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            change = by_key.get(key)
            if change:
                item["value"] = change.translation
        return output
    for change in changes:
        _set_path(output, change.text_key, change.translation)
    return output


def apply_catalog_to_pak(
    source_pak: str,
    entries: Iterable[CatalogEntry],
    output_pak: str,
) -> tuple[TranslationChange, ...]:
    """Write a translated PAK to a new path, leaving the source untouched."""

    from cryengine_localization.adapters.pak import build_pak, normalize_entry_path, scan_pak
    from cryengine_localization.io.json_localization import dump_json, parse_json_relaxed
    from cryengine_localization.core.catalog import catalog_from_json

    if Path(source_pak).expanduser().resolve() == Path(output_pak).expanduser().resolve():
        raise ValueError("output PAK must differ from source PAK")
    source_entries = list(entries)
    changes = tuple(plan_translation_changes(source_entries))
    by_path: dict[str, list[CatalogEntry]] = {}
    for entry in source_entries:
        if entry.translation and entry.status not in {"stale", "orphaned", "invalid"}:
            canonical_path = normalize_entry_path(entry.source_path)
            by_path.setdefault(canonical_path, []).append(entry)
    archive = scan_pak(source_pak)
    archive_paths = {entry.path for entry in archive.entries}
    unknown_paths = sorted(set(by_path) - archive_paths)
    if unknown_paths:
        raise ValueError("translation source path is absent from PAK: " + ", ".join(unknown_paths))
    payload: dict[str, bytes] = {}
    from zipfile import ZipFile

    with ZipFile(archive.path, "r") as source:
        for archive_entry in archive.entries:
            raw = source.read(archive_entry.source_name)
            path_entries = by_path.get(archive_entry.path, [])
            if path_entries and archive_entry.path.casefold().endswith(".json"):
                data = parse_json_relaxed(raw)
                current_by_id = {
                    item.resource_id: item
                    for item in catalog_from_json(archive_entry.path, data)
                }
                for requested in path_entries:
                    current = current_by_id.get(requested.resource_id)
                    if current is None:
                        raise ValueError(f"translation resource is absent from source: {requested.resource_id}")
                    if current.original_hash != requested.original_hash:
                        raise ValueError(f"source changed since catalog export: {requested.resource_id}")
                raw = dump_json(apply_catalog_to_json(data, path_entries))
            payload[archive_entry.path] = raw
    build_pak(payload, output_pak)
    return changes
