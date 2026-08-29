"""War of Rights localization path and language configuration rules."""

from __future__ import annotations

import difflib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


ENGLISH_PREFIX = "localization/english/"
LANGUAGE_PRECEDENCE = ("command_line", "autoexec.cfg", "default")


class DuplicateEnglishPathError(ValueError):
    """An overlay would duplicate an official English localization path."""


def reject_duplicate_english_overlay(
    source_paths: list[str] | tuple[str, ...], overlay_paths: list[str] | tuple[str, ...]
) -> None:
    source = {
        path.replace("\\", "/").casefold()
        for path in source_paths
        if path.replace("\\", "/").casefold().startswith(ENGLISH_PREFIX)
    }
    collisions = sorted(
        path
        for path in overlay_paths
        if path.replace("\\", "/").casefold() in source
    )
    if collisions:
        raise DuplicateEnglishPathError(
            "overlay duplicates official English paths: " + ", ".join(collisions)
        )


@dataclass(frozen=True)
class ConfigPreview:
    before: str
    after: str
    diff: tuple[str, ...]


def preview_language_config(config_text: str, language: str = "english") -> ConfigPreview:
    """Preview a minimal, line-preserving language setting update."""

    if not language or "\n" in language or "\r" in language:
        raise ValueError("language must be a single line")
    lines = config_text.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in config_text else "\n"
    replacements = {
        "g_language": f"g_language={language}{newline}",
        "Localization.Language": f"Localization.Language={language}{newline}",
    }
    found = set()
    for index, line in enumerate(lines):
        match = re.match(r"^\s*(g_language|Localization\.Language)\s*=", line, re.IGNORECASE)
        if match:
            key = match.group(1)
            canonical = "g_language" if key.casefold() == "g_language" else "Localization.Language"
            lines[index] = replacements[canonical]
            found.add(canonical)
    if lines and not lines[-1].endswith(("\n", "\r")):
        lines[-1] += newline
    for key in replacements:
        if key not in found:
            lines.append(replacements[key])
    after = "".join(lines)
    diff = tuple(difflib.unified_diff(config_text.splitlines(), after.splitlines(), fromfile="before", tofile="after"))
    return ConfigPreview(config_text, after, diff)


@dataclass(frozen=True)
class BackupRecord:
    source: Path
    backup: Path
    sha256: str
    size: int


def backup_file(source: str | Path, backup_dir: str | Path) -> BackupRecord:
    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    destination_dir = Path(backup_dir).expanduser().resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source_path.name
    shutil.copy2(source_path, destination)
    import hashlib

    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    return BackupRecord(source_path, destination, digest, source_path.stat().st_size)


def restore_backup(record: BackupRecord) -> Path:
    if not record.backup.is_file():
        raise FileNotFoundError(record.backup)
    import hashlib

    backup_digest = hashlib.sha256(record.backup.read_bytes()).hexdigest()
    if backup_digest != record.sha256:
        raise ValueError(f"backup hash mismatch: {record.backup}")
    shutil.copy2(record.backup, record.source)
    restored_digest = hashlib.sha256(record.source.read_bytes()).hexdigest()
    if restored_digest != record.sha256:
        raise ValueError(f"restored file hash mismatch: {record.source}")
    return record.source
