"""Safe construction of minimal translation overlays from a batch catalog."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import tempfile
from typing import Iterable

from cryengine_localization.adapters.batch_resources import LOOSE_ARCHIVE, ScanIssue, discover_gfx_resources
from cryengine_localization.adapters.gfxfont import (
    GfxNoFontSlotsError,
    GfxToolError,
    replace_font_slots,
    scan_gfx_fonts,
)
from cryengine_localization.adapters.pak import build_pak, normalize_entry_path, read_pak_members
from cryengine_localization.core.apply import apply_catalog_to_json
from cryengine_localization.core.catalog import CatalogEntry, catalog_from_json_bytes
from cryengine_localization.core.manifest import sha256_file
from cryengine_localization.core.stale import validate_translation
from cryengine_localization.io.csv_codec import import_catalog
from cryengine_localization.io.json_localization import dump_json, parse_json_relaxed
from cryengine_localization.io.spreadsheetml import apply_catalog_to_spreadsheetml_bytes


_NON_WRITABLE_STATUSES = frozenset({"stale", "orphaned", "invalid", "report-only"})
_WRITABLE_SUFFIXES = frozenset({".json", ".xml"})


@dataclass(frozen=True)
class BatchSourceArchive:
    archive_path: str
    sha256: str


@dataclass(frozen=True)
class BatchTranslationBuild:
    output_pak: Path
    written_paths: tuple[str, ...]
    skipped_report_only: tuple[str, ...]
    source_archives: tuple[BatchSourceArchive, ...]


@dataclass(frozen=True)
class BatchFontBuild:
    output_pak: Path
    replaced_paths: tuple[str, ...]
    skipped_paths: tuple[str, ...]
    discovery_issues: tuple[ScanIssue, ...]


def _relative_path(root: Path, value: str, *, label: str) -> Path:
    normalized = normalize_entry_path(value)
    candidate = (root / Path(*normalized.split("/"))).absolute()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes the game root: {value}") from exc
    return candidate


def _assert_output_is_external(root: Path, output_pak: Path) -> None:
    try:
        output_pak.relative_to(root)
    except ValueError:
        return
    raise ValueError("batch output must be outside the game root")


def _unqualified_entry(entry: CatalogEntry) -> CatalogEntry:
    prefix = f"{entry.source_archive}::"
    if not entry.resource_id.startswith(prefix):
        raise ValueError(f"batch resource_id does not match source archive: {entry.resource_id}")
    return replace(
        entry,
        resource_id=entry.resource_id.removeprefix(prefix),
        source_path=normalize_entry_path(entry.source_path),
        source_archive="",
    )


def _validate_json_entries(resource_path: str, raw: bytes, entries: Iterable[CatalogEntry]) -> None:
    current = catalog_from_json_bytes(resource_path, raw)
    by_id = {entry.resource_id: entry for entry in current}
    by_key_hash: dict[tuple[str, str], list[CatalogEntry]] = {}
    for entry in current:
        by_key_hash.setdefault((entry.text_key, entry.original_hash), []).append(entry)
    for requested in entries:
        actual = by_id.get(requested.resource_id)
        if actual is None:
            matches = by_key_hash.get((requested.text_key, requested.original_hash), [])
            actual = matches.pop(0) if matches else None
        if actual is None:
            raise ValueError(f"translation resource is absent from source: {requested.resource_id}")
        if actual.original_hash != requested.original_hash:
            raise ValueError(f"source changed since catalog export: {requested.resource_id}")


def _apply_resource(resource_path: str, raw: bytes, entries: list[CatalogEntry]) -> bytes:
    suffix = Path(resource_path).suffix.casefold()
    if suffix == ".json":
        _validate_json_entries(resource_path, raw, entries)
        return dump_json(apply_catalog_to_json(parse_json_relaxed(raw), entries))
    if suffix == ".xml":
        return apply_catalog_to_spreadsheetml_bytes(resource_path, raw, entries)
    raise ValueError(f"unsupported batch translation resource: {resource_path}")


def build_batch_translation_overlay(
    game_root: str | Path,
    entries: Iterable[CatalogEntry],
    output_pak: str | Path,
) -> BatchTranslationBuild:
    """Build a minimal overlay PAK from human-translated batch catalog rows.

    The resulting PAK contains only changed JSON/SpreadsheetML members.  Its
    member paths are the exact original virtual paths, while output itself must
    live outside the game root so no installed game package can be overwritten.
    """

    root = Path(game_root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    output = Path(output_pak).expanduser().resolve()
    _assert_output_is_external(root, output)

    source_entries = list(entries)
    report_only = tuple(sorted(entry.resource_id for entry in source_entries if entry.translation and entry.status == "report-only"))
    grouped: dict[str, dict[str, list[CatalogEntry]]] = {}
    for entry in source_entries:
        if not entry.translation or entry.status in _NON_WRITABLE_STATUSES:
            continue
        if not entry.source_archive:
            raise ValueError(f"batch translation is missing source_archive: {entry.resource_id}")
        resource_path = normalize_entry_path(entry.source_path)
        if Path(resource_path).suffix.casefold() not in _WRITABLE_SUFFIXES:
            raise ValueError(f"unsupported batch translation resource: {resource_path}")
        validate_translation(entry.original_text, entry.translation)
        grouped.setdefault(entry.source_archive, {}).setdefault(resource_path, []).append(
            _unqualified_entry(entry)
        )
    if not grouped:
        raise ValueError("no writable translated entries to build")

    owners: dict[str, str] = {}
    for archive_path, members in grouped.items():
        for resource_path in members:
            owner = owners.setdefault(resource_path.casefold(), archive_path)
            if owner != archive_path:
                raise ValueError(
                    f"translation path appears in multiple source archives: {resource_path} ({owner}, {archive_path})"
                )

    output_members: dict[str, bytes] = {}
    source_archives: list[BatchSourceArchive] = []
    for archive_path in sorted(grouped, key=str.casefold):
        member_entries = grouped[archive_path]
        if archive_path == LOOSE_ARCHIVE:
            raw_by_member = {
                resource_path: _relative_path(root, resource_path, label="loose source path").read_bytes()
                for resource_path in member_entries
            }
        else:
            source_pak = _relative_path(root, archive_path, label="source archive")
            if source_pak.suffix.casefold() != ".pak" or not source_pak.is_file():
                raise FileNotFoundError(f"source archive does not exist: {archive_path}")
            source_archives.append(BatchSourceArchive(archive_path, sha256_file(source_pak)))
            raw_by_member = read_pak_members(source_pak, member_entries)
        for resource_path, resource_entries in member_entries.items():
            output_members[resource_path] = _apply_resource(
                resource_path,
                raw_by_member[resource_path],
                resource_entries,
            )

    build_pak(output_members, output)
    return BatchTranslationBuild(
        output_pak=output,
        written_paths=tuple(sorted(output_members, key=str.casefold)),
        skipped_report_only=report_only,
        source_archives=tuple(source_archives),
    )


def build_batch_translation_overlay_from_csv(
    game_root: str | Path,
    catalog_csv: str | Path,
    output_pak: str | Path,
) -> BatchTranslationBuild:
    """CSV convenience wrapper used by the profile-backed workflow."""

    return build_batch_translation_overlay(game_root, import_catalog(catalog_csv), output_pak)


def build_batch_font_overlay(
    game_root: str | Path,
    font_file: str | Path,
    output_pak: str | Path,
    *,
    ffdec_cli: str | Path | None = None,
) -> BatchFontBuild:
    """Replace every discovered GFX/CFX font slot with one selected font.

    GFX files are staged in a temporary directory and the final PAK is written
    only after every discovered slot has been processed successfully.  Source
    PAKs and loose resources are never changed.
    """

    root = Path(game_root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    output = Path(output_pak).expanduser().resolve()
    _assert_output_is_external(root, output)
    font = Path(font_file).expanduser().resolve()
    if not font.is_file():
        raise FileNotFoundError(font)
    # Output is required to sit outside the game root, so it cannot be found
    # by discovery and does not need an exclusion rule.
    discovery = discover_gfx_resources(root)
    if not discovery.resources:
        raise ValueError("no GFX/CFX resources found below the game root")

    owners: dict[str, str] = {}
    grouped: dict[str, list[str]] = {}
    for resource in discovery.resources:
        owner = owners.setdefault(resource.resource_path.casefold(), resource.archive_path)
        if owner != resource.archive_path:
            raise ValueError(
                f"font path appears in multiple source archives: {resource.resource_path} ({owner}, {resource.archive_path})"
            )
        grouped.setdefault(resource.archive_path, []).append(resource.resource_path)

    raw_resources: list[tuple[str, str, bytes]] = []
    for archive_path in sorted(grouped, key=str.casefold):
        member_paths = sorted(grouped[archive_path], key=str.casefold)
        if archive_path == LOOSE_ARCHIVE:
            raw_resources.extend(
                (
                    archive_path,
                    resource_path,
                    _relative_path(root, resource_path, label="loose GFX source path").read_bytes(),
                )
                for resource_path in member_paths
            )
            continue
        source_pak = _relative_path(root, archive_path, label="GFX source archive")
        raw_by_member = read_pak_members(source_pak, member_paths)
        raw_resources.extend(
            (archive_path, resource_path, raw_by_member[resource_path])
            for resource_path in member_paths
        )

    output_members: dict[str, bytes] = {}
    skipped: list[str] = []
    with tempfile.TemporaryDirectory(prefix="cryengine_batch_fonts_") as temporary_directory:
        temporary = Path(temporary_directory)
        for index, (archive_path, resource_path, raw) in enumerate(raw_resources):
            source = temporary / f"{index:04d}.source.gfx"
            candidate = temporary / f"{index:04d}.patched.gfx"
            source.write_bytes(raw)
            try:
                slots = scan_gfx_fonts(source, ffdec_cli)
            except GfxNoFontSlotsError:
                skipped.append(resource_path)
                continue
            if not slots:
                skipped.append(resource_path)
                continue
            try:
                replacements = {slot.character_id: font for slot in slots}
                replace_font_slots(source, candidate, replacements, ffdec_cli=ffdec_cli)
                if not candidate.is_file() or candidate.stat().st_size == 0:
                    raise GfxToolError("font replacement produced no output")
            except (OSError, ValueError, GfxToolError) as exc:
                raise GfxToolError(f"{archive_path}:{resource_path}: {exc}") from exc
            output_members[resource_path] = candidate.read_bytes()

    if not output_members:
        raise ValueError("no embedded GFX font slots were discovered")
    build_pak(output_members, output)
    return BatchFontBuild(
        output_pak=output,
        replaced_paths=tuple(sorted(output_members, key=str.casefold)),
        skipped_paths=tuple(sorted(skipped, key=str.casefold)),
        discovery_issues=discovery.issues,
    )
