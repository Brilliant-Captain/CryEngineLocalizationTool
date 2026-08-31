"""Read-only discovery of localizable resources across a game tree.

The batch scanner intentionally separates writable catalogs from text evidence.
JSON and SpreadsheetML rows can later be built into an overlay.  Strings found
inside GFX and other opaque resources are report-only: they make missed text
visible without pretending that rewriting a Scaleform movie is safe.
"""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from cryengine_localization.adapters.pak import PakError, read_pak_members, scan_pak
from cryengine_localization.core.catalog import CatalogEntry, catalog_from_json_bytes
from cryengine_localization.io.spreadsheetml import catalog_from_spreadsheetml_bytes


GFX_SUFFIXES = frozenset({".gfx", ".cfx", ".swf"})
FONT_GFX_SUFFIXES = frozenset({".gfx", ".cfx"})
REPORT_ONLY_SUFFIXES = GFX_SUFFIXES | frozenset({".txt", ".loc", ".ini", ".cfg", ".lua"})
SCANNED_SUFFIXES = REPORT_ONLY_SUFFIXES | frozenset({".json", ".xml"})
LOOSE_ARCHIVE = "[loose]"
_MIN_STRING_LENGTH = 4
_FORMAT_MARKERS = frozenset({"GFX", "CFX", "FWS", "CWS"})


@dataclass(frozen=True)
class ArchiveScan:
    """A PAK successfully read during discovery."""

    archive_path: str
    member_count: int


@dataclass(frozen=True)
class TextCandidate:
    """A non-writable string found in an opaque or generic text resource."""

    archive_path: str
    resource_path: str
    resource_type: str
    offset: int
    encoding: str
    text: str


@dataclass(frozen=True)
class ScanIssue:
    """One resource that could not be cataloged, without aborting the scan."""

    archive_path: str
    resource_path: str | None
    kind: str
    detail: str


@dataclass(frozen=True)
class BatchScanReport:
    archives: tuple[ArchiveScan, ...]
    text_candidates: tuple[TextCandidate, ...]
    issues: tuple[ScanIssue, ...]

    @property
    def gfx_candidates(self) -> tuple[TextCandidate, ...]:
        """Compatibility-friendly view of report-only GFX candidates."""

        return tuple(candidate for candidate in self.text_candidates if candidate.resource_type == "gfx")


@dataclass(frozen=True)
class BatchResourceScan:
    catalog: tuple[CatalogEntry, ...]
    report: BatchScanReport


@dataclass(frozen=True)
class GfxResource:
    """A GFX/CFX member location preserving its game-visible virtual path."""

    archive_path: str
    resource_path: str


@dataclass(frozen=True)
class GfxResourceDiscovery:
    resources: tuple[GfxResource, ...]
    issues: tuple[ScanIssue, ...]


def _is_excluded(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def _relative_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def _qualified_entry(entry: CatalogEntry, archive_path: str) -> CatalogEntry:
    return replace(
        entry,
        resource_id=f"{archive_path}::{entry.resource_id}",
        source_archive=archive_path,
    )


def _iter_ascii_strings(raw: bytes) -> Iterable[tuple[int, str]]:
    """Yield bounded printable strings with byte offsets from arbitrary bytes."""

    start: int | None = None
    buffer = bytearray()
    for offset, value in enumerate(raw):
        if 0x20 <= value <= 0x7E:
            if start is None:
                start = offset
            buffer.append(value)
            continue
        if start is not None:
            text = buffer.decode("ascii")
            if (
                len(text) >= _MIN_STRING_LENGTH
                and text not in _FORMAT_MARKERS
                and any(character.isalpha() for character in text)
            ):
                yield start, text
            start = None
            buffer.clear()
    if start is not None:
        text = buffer.decode("ascii")
        if (
            len(text) >= _MIN_STRING_LENGTH
            and text not in _FORMAT_MARKERS
            and any(character.isalpha() for character in text)
        ):
            yield start, text


def _iter_json_string_literals(raw: bytes) -> Iterable[tuple[int, str]]:
    """Yield valid quoted JSON literals even when the outer document is broken."""

    start: int | None = None
    buffer = bytearray()
    escaped = False
    for offset, value in enumerate(raw):
        if start is None:
            if value == ord('"'):
                start = offset
                buffer = bytearray(b'"')
                escaped = False
            continue
        buffer.append(value)
        if escaped:
            escaped = False
            continue
        if value == ord("\\"):
            escaped = True
            continue
        if value != ord('"'):
            continue
        try:
            text = json.loads(buffer.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        else:
            if isinstance(text, str) and text and any(character.isalpha() for character in text):
                yield start, text
        start = None
        buffer = bytearray()


def _report_only_rows(
    archive_path: str,
    resource_path: str,
    resource_type: str,
    raw: bytes,
    *,
    strings: Iterable[tuple[int, str]] | None = None,
) -> tuple[list[CatalogEntry], list[TextCandidate]]:
    rows: list[CatalogEntry] = []
    candidates: list[TextCandidate] = []
    for offset, text in strings if strings is not None else _iter_ascii_strings(raw):
        text_key = f"raw@0x{offset:08X}"
        candidates.append(
            TextCandidate(
                archive_path=archive_path,
                resource_path=resource_path,
                resource_type=resource_type,
                offset=offset,
                encoding="ascii",
                text=text,
            )
        )
        rows.append(
            CatalogEntry(
                resource_id=f"{archive_path}::{resource_path}:{text_key}",
                source_path=resource_path,
                text_key=text_key,
                original_text=text,
                original_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                status="report-only",
                source_archive=archive_path,
            )
        )
    return rows, candidates


def _scan_member(
    archive_path: str,
    resource_path: str,
    raw: bytes,
    catalog: list[CatalogEntry],
    candidates: list[TextCandidate],
    issues: list[ScanIssue],
) -> None:
    suffix = Path(resource_path).suffix.casefold()
    if suffix == ".json":
        try:
            entries = catalog_from_json_bytes(resource_path, raw)
        except (UnicodeDecodeError, ValueError) as exc:
            issues.append(ScanIssue(archive_path, resource_path, "json", str(exc)))
            rows, found = _report_only_rows(
                archive_path,
                resource_path,
                "json",
                raw,
                strings=_iter_json_string_literals(raw),
            )
            catalog.extend(rows)
            candidates.extend(found)
        else:
            if resource_path.casefold().startswith("localization/"):
                catalog.extend(_qualified_entry(entry, archive_path) for entry in entries)
            else:
                catalog.extend(
                    replace(_qualified_entry(entry, archive_path), status="report-only")
                    for entry in entries
                )
        return
    if suffix == ".xml":
        try:
            catalog.extend(
                _qualified_entry(entry, archive_path)
                for entry in catalog_from_spreadsheetml_bytes(resource_path, raw)
            )
            return
        except ValueError:
            # Non-SpreadsheetML XML is still useful evidence, but never becomes
            # writable because attribute/text-node round-tripping is not safe.
            try:
                ElementTree.fromstring(raw)
            except (ElementTree.ParseError, UnicodeDecodeError) as exc:
                issues.append(ScanIssue(archive_path, resource_path, "xml", str(exc)))
                return
            rows, found = _report_only_rows(archive_path, resource_path, "xml", raw)
            catalog.extend(rows)
            candidates.extend(found)
            return
    if suffix in REPORT_ONLY_SUFFIXES:
        resource_type = "gfx" if suffix in GFX_SUFFIXES else suffix.lstrip(".")
        rows, found = _report_only_rows(archive_path, resource_path, resource_type, raw)
        catalog.extend(rows)
        candidates.extend(found)


def scan_game_resources(
    game_root: str | Path,
    *,
    exclude_roots: Iterable[str | Path] = (),
) -> BatchResourceScan:
    """Scan PAK and loose candidates without extracting or writing game assets."""

    root = Path(game_root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    excluded = tuple(Path(value).expanduser().resolve() for value in exclude_roots)
    catalog: list[CatalogEntry] = []
    archives: list[ArchiveScan] = []
    candidates: list[TextCandidate] = []
    issues: list[ScanIssue] = []

    pak_paths = sorted(
        (path for path in root.rglob("*.pak") if not _is_excluded(path.resolve(), excluded)),
        key=lambda path: _relative_path(root, path).casefold(),
    )
    for pak_path in pak_paths:
        archive_path = _relative_path(root, pak_path)
        try:
            archive = scan_pak(pak_path)
            archives.append(ArchiveScan(archive_path, len(archive.entries)))
            member_paths = [
                entry.path
                for entry in archive.entries
                if Path(entry.path).suffix.casefold() in SCANNED_SUFFIXES
            ]
            payload = read_pak_members(pak_path, member_paths) if member_paths else {}
        except (OSError, PakError, ValueError) as exc:
            issues.append(ScanIssue(archive_path, None, "pak", str(exc)))
            continue
        for resource_path in sorted(payload, key=str.casefold):
            _scan_member(archive_path, resource_path, payload[resource_path], catalog, candidates, issues)

    loose_paths = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix.casefold() in SCANNED_SUFFIXES
            and path.suffix.casefold() != ".pak"
            and not _is_excluded(path.resolve(), excluded)
        ),
        key=lambda path: _relative_path(root, path).casefold(),
    )
    for loose_path in loose_paths:
        resource_path = _relative_path(root, loose_path)
        try:
            raw = loose_path.read_bytes()
        except OSError as exc:
            issues.append(ScanIssue(LOOSE_ARCHIVE, resource_path, "file", str(exc)))
            continue
        _scan_member(LOOSE_ARCHIVE, resource_path, raw, catalog, candidates, issues)

    catalog.sort(key=lambda entry: entry.resource_id)
    candidates.sort(key=lambda item: (item.archive_path, item.resource_path, item.offset))
    issues.sort(key=lambda item: (item.archive_path, item.resource_path or "", item.kind))
    return BatchResourceScan(
        catalog=tuple(catalog),
        report=BatchScanReport(tuple(archives), tuple(candidates), tuple(issues)),
    )


def discover_gfx_resources(
    game_root: str | Path,
    *,
    exclude_roots: Iterable[str | Path] = (),
) -> GfxResourceDiscovery:
    """Find every replaceable GFX/CFX resource without extracting its payload.

    Unreadable non-ZIP PAKs are reported and skipped.  They do not make a
    batch font operation fail on their own because no GFX member could be
    identified inside them; failures for an actually discovered GFX are
    handled by the font builder.
    """

    root = Path(game_root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    excluded = tuple(Path(value).expanduser().resolve() for value in exclude_roots)
    resources: list[GfxResource] = []
    issues: list[ScanIssue] = []
    pak_paths = sorted(
        (path for path in root.rglob("*.pak") if not _is_excluded(path.resolve(), excluded)),
        key=lambda path: _relative_path(root, path).casefold(),
    )
    for pak_path in pak_paths:
        archive_path = _relative_path(root, pak_path)
        try:
            archive = scan_pak(pak_path)
        except (OSError, PakError, ValueError) as exc:
            issues.append(ScanIssue(archive_path, None, "pak", str(exc)))
            continue
        resources.extend(
            GfxResource(archive_path, entry.path)
            for entry in archive.entries
            if Path(entry.path).suffix.casefold() in FONT_GFX_SUFFIXES
        )
    loose_paths = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix.casefold() in FONT_GFX_SUFFIXES
            and not _is_excluded(path.resolve(), excluded)
        ),
        key=lambda path: _relative_path(root, path).casefold(),
    )
    resources.extend(GfxResource(LOOSE_ARCHIVE, _relative_path(root, path)) for path in loose_paths)
    resources.sort(key=lambda item: (item.archive_path.casefold(), item.resource_path.casefold()))
    issues.sort(key=lambda item: (item.archive_path.casefold(), item.resource_path or "", item.kind))
    return GfxResourceDiscovery(tuple(resources), tuple(issues))
