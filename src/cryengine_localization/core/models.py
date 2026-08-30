"""Immutable models shared by the localization pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PakEntry:
    """A normalized file entry inside a PAK archive."""

    path: str
    size: int
    compressed_size: int
    crc32: int
    source_name: str


@dataclass(frozen=True)
class PakArchive:
    """Scanned metadata for one PAK file."""

    path: Path
    entries: tuple[PakEntry, ...]


@dataclass(frozen=True)
class ProjectInfo:
    """CryEngine project detection result."""

    path: Path
    engine: str
    confidence: float
    has_cryproject: bool
    has_assets: bool
    pak_files: tuple[Path, ...]
    engine_version: str | None = None
    engine_version_source: str | None = None
    engine_generation_hint: str | None = None
