"""CryEngine project discovery and version hints."""

from __future__ import annotations

import json
from pathlib import Path

from cryengine_localization.core.models import ProjectInfo


def _engine_version(project_file: Path) -> str | None:
    try:
        data = json.loads(project_file.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    for key in ("engine_version", "engineVersion", "version"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    require = data.get("require")
    if isinstance(require, str) and require.strip():
        return require.strip()
    if isinstance(require, dict):
        for key in ("version", "engine_version"):
            value = require.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
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
    if not (has_cryproject or has_assets or pak_files):
        return ProjectInfo(root, "Unknown", 0.0, False, False, ())
    return ProjectInfo(
        path=root,
        engine="CryEngine",
        confidence=min(score, 1.0),
        has_cryproject=has_cryproject,
        has_assets=has_assets,
        pak_files=pak_files,
        engine_version=_engine_version(project_files[0]) if project_files else None,
    )
