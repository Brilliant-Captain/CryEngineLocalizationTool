"""CryEngine project discovery and version hints."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
import re
from pathlib import Path

from cryengine_localization.core.models import ProjectInfo


def _normalize_version(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"(?<!\d)(\d+\.\d+(?:\.\d+){0,2})(?!\d)", value.strip())
    return match.group(1) if match else None


def _engine_version(project_file: Path) -> str | None:
    try:
        data = json.loads(project_file.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    for key in ("engine_version", "engineVersion", "version"):
        version = _normalize_version(data.get(key))
        if version:
            return version
    require = data.get("require")
    version = _normalize_version(require)
    if version:
        return version
    if isinstance(require, dict):
        for key in ("version", "engine_version", "engineVersion", "engine"):
            version = _normalize_version(require.get(key))
            if version:
                return version
    return None


class _VsFixedFileInfo(ctypes.Structure):
    _fields_ = [
        ("signature", ctypes.c_uint32),
        ("structure_version", ctypes.c_uint32),
        ("file_version_ms", ctypes.c_uint32),
        ("file_version_ls", ctypes.c_uint32),
        ("product_version_ms", ctypes.c_uint32),
        ("product_version_ls", ctypes.c_uint32),
        ("file_flags_mask", ctypes.c_uint32),
        ("file_flags", ctypes.c_uint32),
        ("file_os", ctypes.c_uint32),
        ("file_type", ctypes.c_uint32),
        ("file_subtype", ctypes.c_uint32),
        ("file_date_ms", ctypes.c_uint32),
        ("file_date_ls", ctypes.c_uint32),
    ]


def _windows_file_version(path: Path) -> str | None:
    """Read a PE file version using the Windows Version API when available."""

    if os.name != "nt":
        return None
    try:
        version_api = ctypes.WinDLL("version", use_last_error=True)
        get_size = version_api.GetFileVersionInfoSizeW
        get_size.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        get_size.restype = wintypes.DWORD
        get_info = version_api.GetFileVersionInfoW
        get_info.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID]
        get_info.restype = wintypes.BOOL
        query = version_api.VerQueryValueW
        query.argtypes = [wintypes.LPCVOID, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
        query.restype = wintypes.BOOL
        handle = wintypes.DWORD()
        size = get_size(str(path), ctypes.byref(handle))
        if not size:
            return None
        buffer = ctypes.create_string_buffer(size)
        if not get_info(str(path), 0, size, buffer):
            return None
        pointer = ctypes.c_void_p()
        length = wintypes.UINT()
        if not query(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)):
            return None
        if length.value < ctypes.sizeof(_VsFixedFileInfo):
            return None
        info = ctypes.cast(pointer, ctypes.POINTER(_VsFixedFileInfo)).contents
        if info.signature != 0xFEEF04BD:
            return None
        parts = (
            info.file_version_ms >> 16,
            info.file_version_ms & 0xFFFF,
            info.file_version_ls >> 16,
            info.file_version_ls & 0xFFFF,
        )
        return ".".join(str(part) for part in parts)
    except (AttributeError, OSError, ValueError):
        return None


def _cry_system_candidates(root: Path) -> tuple[Path, ...]:
    candidates = {root / "CrySystem.dll"}
    for pattern in (
        "Bin*/CrySystem.dll",
        "bin/*/CrySystem.dll",
        "bin/*/*/CrySystem.dll",
    ):
        candidates.update(root.glob(pattern))
    return tuple(sorted(path for path in candidates if path.is_file()))


def _generation_hint(version: str | None, *, has_cryproject: bool, legacy: bool) -> str | None:
    if version:
        match = re.match(r"(\d+)", version)
        if match:
            return f"CryEngine {match.group(1)}"
    if has_cryproject:
        return "CryEngine 5-era"
    if legacy:
        return "CryEngine 2/3-era"
    return None


def identify_project(path: str | Path) -> ProjectInfo:
    """Identify a CryEngine project using conservative local filesystem hints."""

    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    project_files = sorted(root.glob("*.cryproject"))
    assets = root / "Assets"
    asset_paks = tuple(sorted(assets.glob("*.pak"))) if assets.is_dir() else ()
    localization_dirs = [
        child
        for child in root.iterdir()
        if child.is_dir() and child.name.casefold() in {"localization", "localisation"}
    ]
    localization_paks = tuple(
        sorted(path for directory in localization_dirs for path in directory.glob("*.pak"))
    )
    cry_system_files = _cry_system_candidates(root)
    pak_files = tuple(sorted({*asset_paks, *localization_paks}))
    has_cryproject = bool(project_files)
    has_assets = assets.is_dir()
    score = (0.55 if has_cryproject else 0.0) + (0.25 if has_assets else 0.0)
    if asset_paks:
        score += 0.20
    if localization_paks:
        score += 0.35
        has_loose_localization = any(
            any(directory.glob(pattern))
            for directory in localization_dirs
            for pattern in ("*.xml", "*.gfx")
        )
        if has_loose_localization:
            score += 0.10
    if cry_system_files:
        score += 0.60
    if not (has_cryproject or has_assets or pak_files or cry_system_files):
        return ProjectInfo(root, "Unknown", 0.0, False, False, ())
    project_version = _engine_version(project_files[0]) if project_files else None
    version = project_version
    version_source = ".cryproject" if project_version else None
    if version is None:
        for binary in cry_system_files:
            version = _windows_file_version(binary)
            if version:
                version_source = binary.relative_to(root).as_posix()
                break
    legacy_resources = bool(localization_paks) and any(
        path.name.casefold().endswith("_xml.pak") for path in localization_paks
    )
    return ProjectInfo(
        path=root,
        engine="CryEngine",
        confidence=min(score, 1.0),
        has_cryproject=has_cryproject,
        has_assets=has_assets,
        pak_files=pak_files,
        engine_version=version,
        engine_version_source=version_source,
        engine_generation_hint=_generation_hint(
            version, has_cryproject=has_cryproject, legacy=legacy_resources
        ),
    )
