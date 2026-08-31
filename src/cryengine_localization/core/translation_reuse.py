"""Safe reuse of human translations across compatible exported catalogs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from cryengine_localization.core.catalog import CatalogEntry


_NON_REUSABLE_STATUSES = frozenset({"stale", "orphaned", "invalid", "report-only"})


@dataclass(frozen=True)
class TranslationReuseReport:
    target_rows: int
    old_rows: int
    old_translated_rows: int
    copied_translations: int
    exact_resource_id_matches: int
    hash_fallback_matches: int
    preserved_existing_translations: int
    ambiguous_hash_matches: tuple[str, ...]


def _is_usable_old_translation(entry: CatalogEntry) -> bool:
    return bool(entry.translation.strip()) and entry.status not in _NON_REUSABLE_STATUSES


def _unqualified_resource_id(entry: CatalogEntry) -> str:
    prefix = f"{entry.source_archive}::"
    if entry.source_archive and entry.resource_id.startswith(prefix):
        return entry.resource_id.removeprefix(prefix)
    return entry.resource_id.split("::", 1)[-1]


def _same_source(left: CatalogEntry, right: CatalogEntry) -> bool:
    return (
        left.source_path == right.source_path
        and left.text_key == right.text_key
        and left.original_hash == right.original_hash
    )


def reuse_translations(
    target_entries: Iterable[CatalogEntry], old_entries: Iterable[CatalogEntry]
) -> tuple[list[CatalogEntry], TranslationReuseReport]:
    """Copy only source-identical old translations into blank active target rows.

    Exact unqualified ``resource_id`` is preferred because it preserves
    duplicate-key occurrence suffixes.  The source path/key/original hash tuple
    is used only when it has exactly one candidate.  Existing target
    translations are never overwritten.
    """

    target = list(target_entries)
    old = list(old_entries)
    usable = [entry for entry in old if _is_usable_old_translation(entry)]
    by_resource_id: dict[str, list[CatalogEntry]] = {}
    by_hash: dict[tuple[str, str, str], list[CatalogEntry]] = {}
    for entry in usable:
        by_resource_id.setdefault(_unqualified_resource_id(entry), []).append(entry)
        by_hash.setdefault((entry.source_path, entry.text_key, entry.original_hash), []).append(entry)

    merged: list[CatalogEntry] = []
    copied = 0
    exact_matches = 0
    fallback_matches = 0
    preserved = 0
    ambiguous: list[str] = []
    for entry in target:
        if entry.status != "active":
            merged.append(entry)
            continue
        if entry.translation.strip():
            preserved += 1
            merged.append(entry)
            continue
        exact = [
            candidate
            for candidate in by_resource_id.get(_unqualified_resource_id(entry), [])
            if _same_source(entry, candidate)
        ]
        candidate: CatalogEntry | None = None
        if len(exact) == 1:
            candidate = exact[0]
            exact_matches += 1
        elif len(exact) == 0:
            fallback = by_hash.get((entry.source_path, entry.text_key, entry.original_hash), [])
            if len(fallback) == 1:
                candidate = fallback[0]
                fallback_matches += 1
            elif len(fallback) > 1:
                ambiguous.append(entry.resource_id)
        else:
            ambiguous.append(entry.resource_id)
        if candidate is None:
            merged.append(entry)
            continue
        merged.append(replace(entry, translation=candidate.translation))
        copied += 1
    return merged, TranslationReuseReport(
        target_rows=len(target),
        old_rows=len(old),
        old_translated_rows=len(usable),
        copied_translations=copied,
        exact_resource_id_matches=exact_matches,
        hash_fallback_matches=fallback_matches,
        preserved_existing_translations=preserved,
        ambiguous_hash_matches=tuple(sorted(ambiguous)),
    )
