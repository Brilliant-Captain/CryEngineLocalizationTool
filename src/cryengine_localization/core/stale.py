"""Version-aware catalog status and placeholder validation."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Iterable

from cryengine_localization.core.catalog import CatalogEntry


_PLACEHOLDER_RE = re.compile(r"\{[^{}]+\}|%(?:\d+\$)?[sdif]")


def _placeholders(text: str) -> list[str]:
    return sorted(_PLACEHOLDER_RE.findall(text))


def validate_translation(original: str, translation: str) -> None:
    """Ensure format placeholders are neither dropped nor invented."""

    if _placeholders(original) != _placeholders(translation):
        raise ValueError(
            f"placeholder mismatch: expected {_placeholders(original)!r}, got {_placeholders(translation)!r}"
        )


def reconcile_catalog(
    previous_entries: Iterable[CatalogEntry], current_entries: Iterable[CatalogEntry]
) -> list[CatalogEntry]:
    """Mark changes without silently carrying translations across new originals."""

    previous = {entry.resource_id: entry for entry in previous_entries}
    current = list(current_entries)
    result: list[CatalogEntry] = []
    seen: set[str] = set()
    for entry in current:
        seen.add(entry.resource_id)
        old = previous.get(entry.resource_id)
        if old is None:
            result.append(replace(entry, status="new"))
        elif old.original_hash != entry.original_hash:
            result.append(replace(entry, translation="", status="stale"))
        else:
            result.append(replace(entry, translation=old.translation, status="active"))
    for entry in previous.values():
        if entry.resource_id not in seen:
            result.append(replace(entry, status="orphaned"))
    return result

