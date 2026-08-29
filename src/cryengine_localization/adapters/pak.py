"""Safe reader and deterministic writer for ZIP-style CryEngine PAK files."""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Mapping

from cryengine_localization.core.models import PakArchive, PakEntry


class PakError(RuntimeError):
    """Base class for PAK processing failures."""


class PakFormatError(PakError):
    """The input is not a readable ZIP-style PAK."""


class UnsafeEntryPathError(PakError, ValueError):
    """An archive entry would escape its intended root."""


class DuplicateEntryError(PakError, ValueError):
    """Two entries normalize to the same case-insensitive path."""


def normalize_entry_path(name: str) -> str:
    """Return a canonical POSIX path, rejecting traversal and drive paths.

    CryEngine paths are slash-separated even on Windows. Dot segments are
    harmless and removed, while parent segments are rejected rather than
    silently normalized because they are a common archive traversal vector.
    """

    if not isinstance(name, str) or not name or "\x00" in name:
        raise UnsafeEntryPathError(f"unsafe entry name: {name!r}")
    replaced = name.replace("\\", "/")
    if replaced.startswith("/"):
        raise UnsafeEntryPathError(f"absolute entry name: {name!r}")
    raw_parts = replaced.split("/")
    if raw_parts and ":" in raw_parts[0]:
        raise UnsafeEntryPathError(f"drive-qualified entry name: {name!r}")
    if ".." in raw_parts:
        raise UnsafeEntryPathError(f"parent traversal in entry name: {name!r}")
    parts = [part for part in raw_parts if part not in ("", ".")]
    if not parts:
        raise UnsafeEntryPathError(f"empty entry name: {name!r}")
    return str(PurePosixPath(*parts))


def _open_zip(path: Path) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(path, "r")
    except (FileNotFoundError, IsADirectoryError):
        raise
    except zipfile.BadZipFile as exc:
        raise PakFormatError(f"{path} is not a ZIP-style PAK") from exc


def scan_pak(path: str | Path) -> PakArchive:
    """Scan a PAK without extracting it or writing to the source path."""

    pak_path = Path(path).expanduser().resolve()
    entries: list[PakEntry] = []
    seen: dict[str, str] = {}
    try:
        archive = _open_zip(pak_path)
    except zipfile.BadZipFile as exc:  # defensive for custom ZipFile implementations
        raise PakFormatError(f"{pak_path} is not a ZIP-style PAK") from exc
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            normalized = normalize_entry_path(info.filename)
            folded = normalized.casefold()
            if folded in seen:
                raise DuplicateEntryError(
                    f"duplicate normalized entry: {seen[folded]!r} and {info.filename!r}"
                )
            seen[folded] = info.filename
            entries.append(
                PakEntry(
                    path=normalized,
                    size=info.file_size,
                    compressed_size=info.compress_size,
                    crc32=info.CRC,
                    source_name=info.filename,
                )
            )
    return PakArchive(path=pak_path, entries=tuple(entries))


def read_entry(path: str | Path, entry_path: str) -> bytes:
    """Read one normalized entry after validating the whole archive."""

    archive = scan_pak(path)
    normalized = normalize_entry_path(entry_path)
    match = next((entry for entry in archive.entries if entry.path == normalized), None)
    if match is None:
        raise KeyError(normalized)
    with _open_zip(archive.path) as source:
        return source.read(match.source_name)


def extract_pak(
    path: str | Path,
    output_dir: str | Path,
    *,
    match: str | None = None,
    overwrite: bool = False,
) -> tuple[Path, ...]:
    """Safely extract entries below ``output_dir``.

    ``match`` is a simple case-insensitive substring filter intended for CLI
    use; callers needing richer selection can filter ``scan_pak`` themselves.
    """

    import re

    archive = scan_pak(path)
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    pattern = re.compile(match, re.IGNORECASE) if match else None
    written: list[Path] = []
    with _open_zip(archive.path) as source:
        by_path = {entry.path: entry for entry in archive.entries}
        for normalized, entry in by_path.items():
            if pattern and not pattern.search(normalized):
                continue
            destination = (root / Path(*normalized.split("/"))).resolve()
            try:
                destination.relative_to(root)
            except ValueError as exc:
                raise UnsafeEntryPathError(f"entry escapes extraction root: {normalized}") from exc
            if destination.exists() and not overwrite:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read(entry.source_name))
            written.append(destination)
    return tuple(written)


def _entry_bytes(value: bytes | bytearray | memoryview | str | Path) -> bytes:
    if isinstance(value, (str, Path)):
        return Path(value).read_bytes()
    return bytes(value)


def build_pak(entries: Mapping[str, bytes | bytearray | memoryview | str | Path], output: str | Path) -> Path:
    """Build a deterministic PAK atomically from in-memory/file entries."""

    normalized_entries: dict[str, bytes] = {}
    folded_sources: dict[str, str] = {}
    for raw_name, value in entries.items():
        normalized = normalize_entry_path(raw_name)
        folded = normalized.casefold()
        if folded in folded_sources:
            raise DuplicateEntryError(
                f"duplicate normalized entry: {folded_sources[folded]!r} and {raw_name!r}"
            )
        folded_sources[folded] = raw_name
        normalized_entries[normalized] = _entry_bytes(value)

    destination = Path(output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".partial", dir=destination.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for normalized in sorted(normalized_entries):
                info = zipfile.ZipInfo(normalized, date_time=(2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 0
                info.external_attr = 0
                archive.writestr(info, normalized_entries[normalized])
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination

