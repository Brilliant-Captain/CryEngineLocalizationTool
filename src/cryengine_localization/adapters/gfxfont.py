"""Scaleform/CFX font inspection and explicit external-tool integration."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class GfxFormatError(ValueError):
    """Input is not a valid CFX GFX file."""


class GfxToolError(RuntimeError):
    """FFDec or fontTools failed."""


@dataclass(frozen=True)
class FontSlot:
    character_id: int
    font_name: str
    export_name: str | None = None


@dataclass(frozen=True)
class FontCoverage:
    character_count: int
    supported_count: int
    missing: tuple[str, ...]


def validate_gfx_bytes(raw: bytes) -> bytes:
    if len(raw) < 9 or raw[:3] != b"CFX":
        raise GfxFormatError("not a CFX GFX file")
    try:
        return zlib.decompress(raw[8:])
    except zlib.error as exc:
        raise GfxFormatError("invalid compressed CFX payload") from exc


_FONT_RE = re.compile(r'DefineFont3\s*\(chid:\s*(\d+),\s*fn:\s*"([^"]+)"\)')
_EXPORT_RE = re.compile(r'ExportAssets\s*\(chid:\s*(\d+),\s*exp:\s*"([^"]+)"\)')


def parse_ffdec_font_dump(text: str) -> tuple[FontSlot, ...]:
    exports = {int(match.group(1)): match.group(2) for match in _EXPORT_RE.finditer(text)}
    slots: list[FontSlot] = []
    seen: set[int] = set()
    for match in _FONT_RE.finditer(text):
        character_id = int(match.group(1))
        if character_id in seen:
            continue
        seen.add(character_id)
        slots.append(FontSlot(character_id, match.group(2), exports.get(character_id)))
    return tuple(slots)


def _resolve_ffdec(ffdec_cli: str | Path | None) -> Path:
    if ffdec_cli:
        return Path(ffdec_cli).expanduser().resolve()
    from cryengine_localization.core.tools import discover_tools

    info = discover_tools()["ffdec"]
    if info.available and info.path:
        return Path(info.path)
    raise GfxToolError("FFDec is unavailable; pass --ffdec or set FFDEC_CLI")


def scan_gfx_fonts(gfx_path: str | Path, ffdec_cli: str | Path | None = None) -> tuple[FontSlot, ...]:
    path = Path(gfx_path).expanduser().resolve()
    tool = _resolve_ffdec(ffdec_cli)
    validate_gfx_bytes(path.read_bytes())
    try:
        completed = subprocess.run(
            [str(tool), "-dumpSWF", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise GfxToolError(f"FFDec font scan failed: {exc}") from exc
    slots = parse_ffdec_font_dump(completed.stdout + completed.stderr)
    if not slots:
        raise GfxToolError("FFDec output contained no DefineFont3 slots")
    return slots


def build_font_replace_command(
    ffdec_cli: str | Path,
    input_gfx: str | Path,
    output_gfx: str | Path,
    character_id: int,
    font_file: str | Path,
) -> list[str]:
    if character_id < 0:
        raise ValueError("character_id must be non-negative")
    if Path(input_gfx).resolve() == Path(output_gfx).resolve():
        raise ValueError("output GFX must differ from input GFX")
    return [
        str(ffdec_cli),
        "-replace",
        str(input_gfx),
        str(output_gfx),
        str(character_id),
        str(font_file),
    ]


def subset_font(
    font_file: str | Path,
    text_file: str | Path,
    output_file: str | Path,
    *,
    python_executable: str | Path,
) -> Path:
    """Run ``fontTools.subset`` without shell interpolation."""

    command = [
        str(python_executable),
        "-m",
        "fontTools.subset",
        str(font_file),
        f"--output-file={output_file}",
        f"--text-file={text_file}",
        "--layout-features=*",
        "--glyph-names",
        "--symbol-cmap",
        "--name-IDs=*",
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise GfxToolError(f"fontTools subset failed: {exc}") from exc
    result = Path(output_file)
    if not result.is_file() or result.stat().st_size == 0:
        raise GfxToolError(f"fontTools produced no output: {result}")
    return result


def inspect_font_coverage(
    font_file: str | Path,
    text_file: str | Path,
    *,
    python_executable: str | Path,
) -> FontCoverage:
    """Report missing characters using a configured fontTools interpreter."""

    script = (
        "from fontTools.ttLib import TTFont; import json,sys; "
        "font=TTFont(sys.argv[1]); chars=sorted(set(open(sys.argv[2], encoding='utf-8').read())-{'\\n','\\r'}); "
        "cmap={cp for table in font['cmap'].tables for cp in table.cmap}; "
        "missing=[ch for ch in chars if ord(ch) not in cmap]; "
        "print(json.dumps({'character_count':len(chars),'supported_count':len(chars)-len(missing),'missing':missing}, ensure_ascii=False))"
    )
    try:
        completed = subprocess.run(
            [str(python_executable), "-c", script, str(font_file), str(text_file)],
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(completed.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise GfxToolError(f"font coverage inspection failed: {exc}") from exc
    missing = tuple(str(item) for item in data.get("missing", ()))
    return FontCoverage(
        character_count=int(data["character_count"]),
        supported_count=int(data["supported_count"]),
        missing=missing,
    )


def replace_font_slots(
    gfx_path: str | Path,
    output_gfx: str | Path,
    replacements: Mapping[int, str | Path],
    *,
    ffdec_cli: str | Path | None = None,
) -> Path:
    """Replace discovered DefineFont3 slots using FFDec, atomically.

    ``replacements`` maps the actual character IDs reported by
    :func:`scan_gfx_fonts` to TTF/OTF files. The source GFX is never modified;
    each replacement is staged in a temporary file and the final file is
    copied only after all FFDec invocations and a CFX validation succeed.
    """

    source = Path(gfx_path).expanduser().resolve()
    destination = Path(output_gfx).expanduser().resolve()
    if source == destination:
        raise ValueError("output GFX must differ from input GFX")
    if not replacements:
        raise ValueError("at least one font replacement is required")
    tool = _resolve_ffdec(ffdec_cli)
    slots = {slot.character_id for slot in scan_gfx_fonts(source, tool)}
    unknown = sorted(set(replacements) - slots)
    if unknown:
        raise GfxToolError(f"font slot(s) not found in GFX: {unknown}")
    for font_file in replacements.values():
        if not Path(font_file).expanduser().is_file():
            raise FileNotFoundError(font_file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_paths: list[Path] = []
    current = source
    try:
        for character_id, font_file in sorted(replacements.items()):
            fd, name = tempfile.mkstemp(
                prefix=f".{destination.name}.{character_id}.",
                suffix=".gfx.partial",
                dir=destination.parent,
            )
            os.close(fd)
            stage = Path(name)
            temporary_paths.append(stage)
            command = build_font_replace_command(
                tool, current, stage, character_id, font_file
            )
            try:
                subprocess.run(command, check=True, capture_output=True, text=True)
            except (OSError, subprocess.CalledProcessError) as exc:
                raise GfxToolError(f"FFDec font replacement failed for ID {character_id}: {exc}") from exc
            if not stage.is_file() or stage.stat().st_size == 0:
                raise GfxToolError(f"FFDec produced no GFX output for ID {character_id}")
            current = stage
        validate_gfx_bytes(current.read_bytes())
        shutil.copy2(current, destination)
    finally:
        for path in temporary_paths:
            path.unlink(missing_ok=True)
    return destination
