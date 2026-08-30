"""Safe reader and deterministic writer for ZIP-style CryEngine PAK files."""

from __future__ import annotations

import binascii
import bz2
import os
import struct
import tempfile
import zipfile
import zlib
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


_LOCAL_FILE_HEADER = struct.Struct("<4s5H3L2H")
_LOCAL_FILE_SIGNATURE = b"PK\x03\x04"


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


def _read_legacy_member(source: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    """Read a member whose local header differs only by path separators.

    Some CryEngine PAK writers store POSIX separators in the central directory
    and Windows separators in the local header. Python's ``zipfile`` rejects
    that mismatch even though both names normalize to the same safe path.
    """

    if source.fp is None:
        raise PakFormatError("PAK archive is closed")
    source.fp.seek(info.header_offset)
    header = source.fp.read(_LOCAL_FILE_HEADER.size)
    if len(header) != _LOCAL_FILE_HEADER.size:
        raise PakFormatError(f"truncated local header for {info.filename!r}")
    fields = _LOCAL_FILE_HEADER.unpack(header)
    if fields[0] != _LOCAL_FILE_SIGNATURE:
        raise PakFormatError(f"invalid local header for {info.filename!r}")
    flags = fields[2]
    compression = fields[3]
    name_length = fields[9]
    extra_length = fields[10]
    local_name_bytes = source.fp.read(name_length)
    source.fp.seek(extra_length, os.SEEK_CUR)
    encoding = "utf-8" if flags & 0x800 else "cp437"
    try:
        local_name = local_name_bytes.decode(encoding)
    except UnicodeDecodeError as exc:
        raise PakFormatError(f"invalid local entry name for {info.filename!r}") from exc
    if normalize_entry_path(local_name) != normalize_entry_path(info.filename):
        raise PakFormatError(
            f"local and central entry names differ: {local_name!r} != {info.filename!r}"
        )
    if flags & 0x1:
        raise PakFormatError(f"encrypted PAK entries are unsupported: {info.filename!r}")
    if compression != info.compress_type:
        raise PakFormatError(f"local compression differs for {info.filename!r}")
    compressed = source.fp.read(info.compress_size)
    if len(compressed) != info.compress_size:
        raise PakFormatError(f"truncated payload for {info.filename!r}")
    try:
        if compression == zipfile.ZIP_STORED:
            payload = compressed
        elif compression == zipfile.ZIP_DEFLATED:
            payload = zlib.decompress(compressed, -zlib.MAX_WBITS)
        elif compression == zipfile.ZIP_BZIP2:
            payload = bz2.decompress(compressed)
        else:
            raise PakFormatError(
                f"unsupported legacy PAK compression {compression} for {info.filename!r}"
            )
    except (OSError, EOFError, zlib.error) as exc:
        raise PakFormatError(f"cannot decompress {info.filename!r}") from exc
    if len(payload) != info.file_size:
        raise PakFormatError(f"uncompressed size mismatch for {info.filename!r}")
    if binascii.crc32(payload) & 0xFFFFFFFF != info.CRC:
        raise PakFormatError(f"CRC mismatch for {info.filename!r}")
    return payload


def _read_member(source: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    try:
        return source.read(info)
    except zipfile.BadZipFile as exc:
        if "File name in directory" not in str(exc) or "header" not in str(exc):
            raise PakFormatError(f"cannot read PAK entry {info.filename!r}") from exc
        return _read_legacy_member(source, info)


def read_pak_entries(path: str | Path) -> dict[str, bytes]:
    """Read all validated entries keyed by normalized archive path."""

    archive = scan_pak(path)
    payload: dict[str, bytes] = {}
    with _open_zip(archive.path) as source:
        infos = {info.filename: info for info in source.infolist() if not info.is_dir()}
        for entry in archive.entries:
            payload[entry.path] = _read_member(source, infos[entry.source_name])
    return payload


def read_entry(path: str | Path, entry_path: str) -> bytes:
    """Read one normalized entry after validating the whole archive."""

    archive = scan_pak(path)
    normalized = normalize_entry_path(entry_path)
    match = next((entry for entry in archive.entries if entry.path == normalized), None)
    if match is None:
        raise KeyError(normalized)
    with _open_zip(archive.path) as source:
        info = next(item for item in source.infolist() if item.filename == match.source_name)
        return _read_member(source, info)


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
        infos = {info.filename: info for info in source.infolist() if not info.is_dir()}
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
            destination.write_bytes(_read_member(source, infos[entry.source_name]))
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
