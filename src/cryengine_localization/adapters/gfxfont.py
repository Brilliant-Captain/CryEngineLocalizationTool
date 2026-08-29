"""Scaleform/CFX font inspection and explicit external-tool integration."""

from __future__ import annotations

import re
import subprocess
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


class GfxFormatError(ValueError):
    """Input is not a valid CFX GFX file."""


class GfxToolError(RuntimeError):
    """FFDec or fontTools failed."""


@dataclass(frozen=True)
class FontSlot:
    character_id: int
    font_name: str
    export_name: str | None = None


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


def scan_gfx_fonts(gfx_path: str | Path, ffdec_cli: str | Path) -> tuple[FontSlot, ...]:
    path = Path(gfx_path).expanduser().resolve()
    tool = Path(ffdec_cli).expanduser().resolve()
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

