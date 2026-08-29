"""Translation application and dry-run planning."""

from __future__ import annotations

import copy
from dataclasses import dataclass
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

