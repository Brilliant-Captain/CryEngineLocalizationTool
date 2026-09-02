"""Profile-backed orchestration shared by the GUI and CLI."""

from __future__ import annotations

import hashlib
import json
import os
import csv
import shutil
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from cryengine_localization import __version__
from cryengine_localization.adapters.batch_resources import scan_game_resources
from cryengine_localization.adapters.pak import build_pak, read_pak_entries, scan_pak
from cryengine_localization.core.apply import TranslationChange, apply_catalog_to_pak, plan_translation_changes
from cryengine_localization.core.batch_workflow import (
    BatchFontBuild,
    BatchTranslationBuild,
    build_batch_font_overlay,
    build_batch_translation_overlay,
)
from cryengine_localization.core.catalog import CatalogEntry, catalog_from_json_bytes
from cryengine_localization.core.install import (
    InstallItem,
    InstallationRecord,
    InstalledItem,
    install_files,
    plan_install,
    read_install_record,
    rollback_install,
    write_install_record,
)
from cryengine_localization.core.manifest import build_manifest, sha256_file, write_manifest
from cryengine_localization.core.profile import ProfileError, ProjectProfile
from cryengine_localization.core.translation_reuse import TranslationReuseReport, reuse_translations
from cryengine_localization.core.stale import validate_translation
from cryengine_localization.io.csv_codec import export_catalog, export_friendly_catalog, import_catalog
from cryengine_localization.io.spreadsheetml import catalog_from_spreadsheetml_bytes


@dataclass(frozen=True)
class BatchWorkflowBuild:
    translation: BatchTranslationBuild
    font: BatchFontBuild | None
    manifest_path: Path


@dataclass(frozen=True)
class BatchDryRunFailure:
    resource_id: str
    source_path: str
    text_key: str
    reason: str


@dataclass(frozen=True)
class BatchDryRunReport:
    total_rows: int
    ready_count: int
    empty_translation_count: int
    inactive_row_count: int
    failure_count: int
    failures: tuple[BatchDryRunFailure, ...]
    failures_truncated: bool


class BatchPreflightError(ValueError):
    """The compact batch preflight found invalid translations."""

    def __init__(self, report: BatchDryRunReport) -> None:
        self.report = report
        detail = report.failures[0].resource_id if report.failures else "unknown"
        super().__init__(f"batch preflight found {report.failure_count} invalid translation(s); first: {detail}")


@dataclass(frozen=True)
class BatchTranslationProfileBuild:
    translation: BatchTranslationBuild
    manifest_path: Path


@dataclass(frozen=True)
class BatchFontProfileBuild:
    font: BatchFontBuild
    report_path: Path


@dataclass(frozen=True)
class ReportShardGroup:
    resource_type: str
    row_count: int
    files: tuple[str, ...]


@dataclass(frozen=True)
class BatchTranslationReuse:
    catalog_path: Path
    backup_path: Path | None
    report_path: Path | None
    reuse: TranslationReuseReport


_REPORT_ONLY_SHARD_ROWS = 10_000


def _batch_overlay_entries(
    profile: ProjectProfile, entries: list["CatalogEntry"]
) -> list["CatalogEntry"]:
    """Mark resources that cannot load through the chosen overlay mode."""

    if profile.overlay_mode != "english-path-overlay":
        return entries
    return [
        replace(entry, status="report-only")
        if entry.status == "active"
        and not entry.source_path.casefold().startswith("localization/english/")
        else entry
        for entry in entries
    ]


def catalog_from_pak(path: str | Path):
    """Extract catalog rows from JSON and SpreadsheetML entries in a PAK."""

    archive = scan_pak(path)
    payload = read_pak_entries(archive.path)
    rows = []
    for entry in archive.entries:
        try:
            if entry.path.casefold().endswith(".json"):
                rows.extend(catalog_from_json_bytes(entry.path, payload[entry.path]))
            elif entry.path.casefold().endswith(".xml"):
                rows.extend(catalog_from_spreadsheetml_bytes(entry.path, payload[entry.path]))
        except (UnicodeDecodeError, ValueError):
            continue
    return rows


def _profile_entries(profile: ProjectProfile):
    profile.validate(require_files=True)
    entries = import_catalog(profile.translation_csv)
    if profile.overlay_mode == "english-path-overlay":
        entries = [
            entry
            for entry in entries
            if entry.source_path.casefold().startswith("localization/english/")
        ]
    return entries


def export_profile_catalog(profile: ProjectProfile, *, overwrite: bool = False) -> tuple[Path, int]:
    """Export a source PAK catalog to the profile CSV path."""

    profile.validate()
    source = Path(profile.source_pak).expanduser().resolve()
    output = Path(profile.translation_csv).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists() and not overwrite:
        raise FileExistsError(f"translation CSV already exists; pass --overwrite to replace: {output}")
    entries = catalog_from_pak(source)
    export_catalog(entries, output)
    return output, len(entries)


def plan_profile_changes(profile: ProjectProfile) -> list[TranslationChange]:
    """Build the validated Dry-run change list for a profile."""

    return plan_translation_changes(_profile_entries(profile))


def build_profile(profile: ProjectProfile):
    """Build the translated PAK and manifest described by a profile."""

    entries = _profile_entries(profile)
    source = Path(profile.source_pak).expanduser().resolve()
    output = Path(profile.output_pak).expanduser().resolve()
    changes = apply_catalog_to_pak(str(source), entries, str(output))
    replacements = [
        {
            "source_path": change.source_path,
            "text_key": change.text_key,
            "translation_sha256": hashlib.sha256(change.translation.encode("utf-8")).hexdigest(),
        }
        for change in changes
    ]
    manifest = build_manifest(
        tool_version=__version__,
        engine_version=profile.engine_version,
        target_language=profile.language,
        source_packages=[{"path": source.name, "sha256": sha256_file(source)}],
        replacements=replacements,
        font_strategy={
            "mode": "full" if profile.font.enabled else "none",
            "character_ids": [slot.character_id for slot in profile.font.slots],
        },
        output_sha256=sha256_file(output),
        project=profile.name,
        overlay_mode=profile.overlay_mode,
    )
    manifest_path = write_manifest(manifest, profile.manifest)
    return output, manifest_path, changes


def _write_json_atomic(value: object, output_path: str | Path) -> Path:
    destination = Path(output_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".partial", dir=destination.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def _export_catalog_atomic(
    entries: list[CatalogEntry],
    output_path: str | Path,
    *,
    friendly: bool = False,
) -> Path:
    destination = Path(output_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".partial", dir=destination.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        if friendly:
            export_friendly_catalog(entries, temporary)
        else:
            export_catalog(entries, temporary)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def _report_resource_type(entry: CatalogEntry) -> str:
    suffix = Path(entry.source_path).suffix.casefold()
    if suffix in {".gfx", ".cfx", ".swf"}:
        return "gfx"
    if suffix == ".json":
        return "json"
    if suffix == ".xml":
        return "xml"
    return "other"


def write_report_only_shards(
    entries: list[CatalogEntry],
    output_dir: str | Path,
    *,
    rows_per_file: int = _REPORT_ONLY_SHARD_ROWS,
    overwrite: bool = False,
) -> tuple[Path, tuple[ReportShardGroup, ...]]:
    """Write report-only rows in small, type-grouped CSV shards plus an index."""

    if rows_per_file <= 0:
        raise ValueError("rows_per_file must be positive")
    destination = Path(output_dir).expanduser().resolve()
    if destination.exists() and not overwrite:
        raise FileExistsError(f"report shard directory already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    try:
        grouped: dict[str, list["CatalogEntry"]] = {}
        for entry in entries:
            grouped.setdefault(_report_resource_type(entry), []).append(entry)
        index_rows: list[dict[str, str | int]] = []
        summaries: list[ReportShardGroup] = []
        for resource_type in sorted(grouped):
            group_entries = sorted(grouped[resource_type], key=lambda entry: entry.resource_id)
            files: list[str] = []
            for number, start in enumerate(range(0, len(group_entries), rows_per_file), start=1):
                filename = f"{resource_type}-{number:03d}.csv"
                _export_catalog_atomic(group_entries[start : start + rows_per_file], staging / filename)
                row_count = min(rows_per_file, len(group_entries) - start)
                files.append(filename)
                index_rows.append(
                    {
                        "resource_type": resource_type,
                        "file": filename,
                        "row_count": row_count,
                    }
                )
            summaries.append(ReportShardGroup(resource_type, len(group_entries), tuple(files)))
        index_path = staging / "report-index.csv"
        with index_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=("resource_type", "file", "row_count"))
            writer.writeheader()
            writer.writerows(index_rows)
        if destination.exists():
            if not destination.is_dir():
                raise ValueError(f"report shard path is not a directory: {destination}")
            shutil.rmtree(destination)
        os.replace(staging, destination)
        return destination / "report-index.csv", tuple(summaries)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def export_batch_profile_catalog(
    profile: ProjectProfile, *, overwrite: bool = False, friendly: bool = False
) -> tuple[Path, int, Path]:
    """Scan a complete game root and write its human-editable CSV plus report."""

    profile.validate()
    batch = profile.batch.require_scan()
    catalog_path = Path(batch.catalog_csv).expanduser().resolve()
    report_path = Path(batch.scan_report).expanduser().resolve()
    report_parts = report_path.with_name(f"{report_path.stem}-parts")
    if catalog_path.exists() and not overwrite:
        raise FileExistsError(
            f"translation CSV already exists; pass --overwrite to replace: {catalog_path}"
        )
    if (report_path.exists() or report_parts.exists()) and not overwrite:
        raise FileExistsError(
            f"scan report output already exists; pass --overwrite to replace: {report_path}"
        )
    scan = scan_game_resources(batch.game_root)
    entries = _batch_overlay_entries(profile, list(scan.catalog))
    active_entries = [entry for entry in entries if entry.status == "active"]
    report_only_entries = [entry for entry in entries if entry.status == "report-only"]
    _export_catalog_atomic(active_entries, catalog_path, friendly=friendly)
    index_path, shard_groups = write_report_only_shards(
        report_only_entries,
        report_parts,
        overwrite=overwrite,
    )
    report_path = _write_json_atomic(
        {
            "active_catalog_count": len(active_entries),
            "report_only_count": len(report_only_entries),
            "archives": [asdict(archive) for archive in scan.report.archives],
            "issues": [asdict(issue) for issue in scan.report.issues],
            "text_candidate_counts": dict(
                Counter(candidate.resource_type for candidate in scan.report.text_candidates)
            ),
            "report_index": str(index_path.name),
            "report_shards": [
                {
                    "resource_type": group.resource_type,
                    "row_count": group.row_count,
                    "files": list(group.files),
                }
                for group in shard_groups
            ],
        },
        report_path,
    )
    return catalog_path, len(active_entries), report_path


def plan_batch_profile_changes(profile: ProjectProfile) -> list[TranslationChange]:
    """Preview only human-entered writable translations from the batch CSV."""

    profile.validate()
    batch = profile.batch.require_dry_run()
    return plan_translation_changes(_batch_overlay_entries(profile, import_catalog(batch.catalog_csv)))


def plan_batch_profile_report(
    profile: ProjectProfile, *, max_failure_details: int = 100
) -> BatchDryRunReport:
    """Return a bounded preflight summary instead of every successful change."""

    if max_failure_details <= 0:
        raise ValueError("max_failure_details must be positive")
    profile.validate()
    batch = profile.batch.require_dry_run()
    entries = _batch_overlay_entries(profile, import_catalog(batch.catalog_csv))
    ready = 0
    empty = 0
    inactive = 0
    failure_count = 0
    failures: list[BatchDryRunFailure] = []
    for entry in entries:
        if entry.status != "active":
            inactive += 1
            continue
        if not entry.translation.strip():
            empty += 1
            continue
        try:
            validate_translation(entry.original_text, entry.translation)
        except ValueError as exc:
            failure_count += 1
            if len(failures) < max_failure_details:
                failures.append(
                    BatchDryRunFailure(
                        entry.resource_id,
                        entry.source_path,
                        entry.text_key,
                        str(exc),
                    )
                )
            continue
        ready += 1
    return BatchDryRunReport(
        total_rows=len(entries),
        ready_count=ready,
        empty_translation_count=empty,
        inactive_row_count=inactive,
        failure_count=failure_count,
        failures=tuple(failures),
        failures_truncated=failure_count > len(failures),
    )


def _next_reuse_backup_path(catalog_path: Path) -> Path:
    candidate = catalog_path.with_name(f"{catalog_path.stem}.before-reuse{catalog_path.suffix}")
    number = 2
    while candidate.exists():
        candidate = catalog_path.with_name(
            f"{catalog_path.stem}.before-reuse-{number}{catalog_path.suffix}"
        )
        number += 1
    return candidate


def reuse_batch_profile_translations(
    profile: ProjectProfile,
    *,
    old_csv: str | Path | None = None,
    dry_run: bool = False,
) -> BatchTranslationReuse:
    """Safely reuse a prior human-edited catalog in the current active CSV."""

    profile.validate()
    batch = profile.batch.require_dry_run()
    catalog_path = Path(batch.catalog_csv).expanduser().resolve()
    if not catalog_path.is_file():
        raise FileNotFoundError(catalog_path)
    legacy_value = old_csv or batch.legacy_translation_csv
    if not legacy_value:
        raise ProfileError("batch.legacy_translation_csv is required for translation reuse")
    legacy_path = Path(legacy_value).expanduser().resolve()
    if not legacy_path.is_file():
        raise FileNotFoundError(legacy_path)
    merged, reuse = reuse_translations(import_catalog(catalog_path), import_catalog(legacy_path))
    if dry_run:
        return BatchTranslationReuse(catalog_path, None, None, reuse)
    backup_path = _next_reuse_backup_path(catalog_path)
    shutil.copy2(catalog_path, backup_path)
    _export_catalog_atomic(merged, catalog_path)
    report_path = catalog_path.with_name(f"{catalog_path.stem}.reuse-report.json")
    _write_json_atomic(
        {
            "catalog": catalog_path.name,
            "old_catalog": legacy_path.name,
            "backup": backup_path.name,
            "reuse": asdict(reuse),
        },
        report_path,
    )
    return BatchTranslationReuse(catalog_path, backup_path, report_path, reuse)


def _build_batch_manifest(
    profile: ProjectProfile,
    entries: list[CatalogEntry],
    translation: BatchTranslationBuild,
    font: BatchFontBuild | None,
) -> Path:
    batch = profile.batch
    replacements = [
        {
            "source_archive": entry.source_archive,
            "source_path": entry.source_path,
            "text_key": entry.text_key,
            "translation_sha256": hashlib.sha256(entry.translation.encode("utf-8")).hexdigest(),
        }
        for entry in entries
        if entry.translation and entry.status not in {"stale", "orphaned", "invalid", "report-only"}
    ]
    manifest = build_manifest(
        tool_version=__version__,
        engine_version=profile.engine_version,
        target_language=profile.language,
        source_packages=[asdict(source) for source in translation.source_archives],
        replacements=replacements,
        font_strategy=(
            {
                "mode": "batch-all",
                "font_file": Path(batch.font_file).name,
                "output_pak": Path(batch.font_overlay_pak).name,
                "replaced_paths": list(font.replaced_paths),
                "skipped_paths": list(font.skipped_paths),
                "discovery_issue_count": len(font.discovery_issues),
            }
            if font is not None
            else {"mode": "none", "character_ids": []}
        ),
        output_sha256=sha256_file(translation.output_pak),
        project=profile.name,
        overlay_mode=profile.overlay_mode,
    )
    manifest_path = write_manifest(manifest, batch.manifest)
    return manifest_path


def _build_batch_translation(profile: ProjectProfile) -> tuple[list[CatalogEntry], BatchTranslationBuild]:
    profile.validate()
    batch = profile.batch.require_translation_build()
    report = plan_batch_profile_report(profile)
    if report.failure_count:
        raise BatchPreflightError(report)
    entries = _batch_overlay_entries(profile, import_catalog(batch.catalog_csv))
    translation = build_batch_translation_overlay(
        batch.game_root,
        entries,
        batch.translation_overlay_pak,
    )
    return entries, translation


def build_batch_translation_profile(profile: ProjectProfile) -> BatchTranslationProfileBuild:
    """Build only the translation overlay and its manifest."""

    entries, translation = _build_batch_translation(profile)
    manifest_path = _build_batch_manifest(profile, entries, translation, None)
    return BatchTranslationProfileBuild(translation, manifest_path)


def build_batch_font_profile(profile: ProjectProfile) -> BatchFontProfileBuild:
    """Build only the font overlay, without requiring a translation CSV."""

    profile.validate()
    batch = profile.batch.require_font_build()
    font = build_batch_font_overlay(
        batch.game_root,
        batch.font_file,
        batch.font_overlay_pak,
        ffdec_cli=batch.ffdec or None,
    )
    output = Path(batch.font_overlay_pak).expanduser().resolve()
    report_path = output.with_name(f"{output.stem}.font-report.json")
    _write_json_atomic(
        {
            "output_pak": output.name,
            "replaced_paths": list(font.replaced_paths),
            "skipped_paths": list(font.skipped_paths),
            "discovery_issues": [asdict(issue) for issue in font.discovery_issues],
        },
        report_path,
    )
    return BatchFontProfileBuild(font, report_path)


def build_batch_profile(profile: ProjectProfile) -> BatchWorkflowBuild:
    """Build translation/font overlays and a manifest; never install into the game."""

    entries, translation = _build_batch_translation(profile)
    font: BatchFontBuild | None = None
    if profile.batch.font_file:
        font = build_batch_font_profile(profile).font
    manifest_path = _build_batch_manifest(profile, entries, translation, font)
    return BatchWorkflowBuild(translation, font, manifest_path)


def _profile_install_items(profile: ProjectProfile) -> tuple[Path, list[InstallItem]]:
    install = profile.install
    if not install.game_root:
        raise ProfileError("install.game_root is required for installation")
    if not install.backup_dir:
        raise ProfileError("install.backup_dir is required for installation")
    if not install.record:
        raise ProfileError("install.record is required for installation")
    if not install.files:
        raise ProfileError("install.files is required for installation")
    return Path(install.game_root), [InstallItem(Path(item.source), item.destination) for item in install.files]


def plan_profile_install(profile: ProjectProfile) -> list[InstalledItem]:
    """Return a guarded installation plan without writing the game root."""

    root, items = _profile_install_items(profile)
    return plan_install(root, items)


def install_profile(profile: ProjectProfile) -> InstallationRecord:
    """Install profile files with backups and write the configured record."""

    root, items = _profile_install_items(profile)
    install = profile.install
    record = install_files(
        root,
        items,
        backup_dir=install.backup_dir,
        process_names=install.process_names,
    )
    write_install_record(record, install.record)
    return record


def rollback_profile(profile: ProjectProfile) -> InstallationRecord:
    """Rollback the installation record configured by a profile."""

    if not profile.install.record:
        raise ProfileError("install.record is required for rollback")
    record = read_install_record(profile.install.record)
    rollback_install(record)
    return record
