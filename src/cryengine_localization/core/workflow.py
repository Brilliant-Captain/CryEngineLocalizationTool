"""Profile-backed orchestration shared by the GUI and CLI."""

from __future__ import annotations

import hashlib
from pathlib import Path

from cryengine_localization import __version__
from cryengine_localization.adapters.pak import build_pak, read_pak_entries, scan_pak
from cryengine_localization.core.apply import TranslationChange, apply_catalog_to_pak, plan_translation_changes
from cryengine_localization.core.catalog import catalog_from_json_bytes
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
from cryengine_localization.io.csv_codec import export_catalog, import_catalog
from cryengine_localization.io.spreadsheetml import catalog_from_spreadsheetml_bytes


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
