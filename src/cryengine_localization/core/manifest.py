"""Build manifests for reproducible and reversible outputs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    *,
    tool_version: str,
    engine_version: str | None,
    target_language: str,
    source_packages: Iterable[dict[str, Any]],
    replacements: Iterable[dict[str, Any]],
    font_strategy: dict[str, Any],
    build_time_utc: str | None = None,
    output_sha256: str | None = None,
    project: str | None = None,
    overlay_mode: str | None = None,
) -> dict[str, Any]:
    if build_time_utc is None:
        build_time_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "schema_version": 1,
        "tool_version": tool_version,
        "cryengine_version": engine_version or "unknown",
        "project": project,
        "overlay_mode": overlay_mode,
        "target_language": target_language,
        "source_packages": list(source_packages),
        "replacements": list(replacements),
        "font_strategy": font_strategy,
        "build_time_utc": build_time_utc,
        "output_sha256": output_sha256,
    }


def write_manifest(manifest: dict[str, Any], path: str | Path) -> Path:
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination
