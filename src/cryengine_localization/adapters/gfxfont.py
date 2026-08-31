"""Scaleform GFX/CFX font inspection and external-tool integration."""

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

from .swf import DEFINE_FONT3_TAG, GfxContainer, SwfFormatError, decode_gfx_container, replace_define_font3_tags


class GfxFormatError(ValueError):
    """Input is not a supported Scaleform GFX/CFX file."""


class GfxToolError(RuntimeError):
    """FFDec or fontTools failed."""


class GfxNoFontSlotsError(GfxToolError):
    """FFDec read the resource but found no replaceable DefineFont3 slot."""


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


@dataclass(frozen=True)
class GfxRebuildComparison:
    original_size: int
    candidate_size: int
    changed_font_ids: tuple[int, ...]
    non_font_changes: tuple[int, ...]
    tag_count_same: bool
    level: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class GfxSafetyReport:
    path: str
    container: str
    file_size: int
    payload_size: int
    tag_count: int
    font_tag_count: int
    largest_font_tag_size: int
    level: str
    reasons: tuple[str, ...]


def validate_gfx_bytes(raw: bytes) -> bytes:
    if len(raw) < 8:
        raise GfxFormatError("not a supported GFX/CFX file")
    if raw[:3] == b"GFX":
        return raw
    if raw[:3] == b"CFX":
        try:
            return zlib.decompress(raw[8:])
        except zlib.error as exc:
            raise GfxFormatError("invalid compressed CFX payload") from exc
    raise GfxFormatError("not a supported GFX/CFX file")


def _font_id(tag_payload: bytes) -> int | None:
    if len(tag_payload) < 2:
        return None
    return int.from_bytes(tag_payload[:2], "little")


def _container_or_error(path: Path) -> GfxContainer:
    try:
        return decode_gfx_container(path.read_bytes())
    except (OSError, SwfFormatError) as exc:
        raise GfxFormatError(f"unable to parse legacy GFX/CFX file {path}: {exc}") from exc


def compare_gfx_rebuilds(
    original_path: str | Path,
    candidate_path: str | Path,
    character_ids: set[int] | frozenset[int] | None = None,
) -> GfxRebuildComparison:
    """Compare an FFDec candidate with its source at SWF tag level."""

    original = Path(original_path).expanduser().resolve()
    candidate = Path(candidate_path).expanduser().resolve()
    source = _container_or_error(original)
    rebuilt = _container_or_error(candidate)
    reasons: list[str] = []
    changed_fonts: list[int] = []
    non_font_changes: list[int] = []
    tag_count_same = len(source.tags) == len(rebuilt.tags)
    if not tag_count_same:
        reasons.append("tag counts differ")
    if source.payload_header != rebuilt.payload_header:
        reasons.append("internal Scaleform headers differ")
    if source.magic != rebuilt.magic:
        reasons.append("container kinds differ")
    if tag_count_same:
        for index, (left, right) in enumerate(zip(source.tags, rebuilt.tags)):
            if left.code != right.code:
                non_font_changes.append(index)
                continue
            if left.raw == right.raw:
                continue
            if left.code == DEFINE_FONT3_TAG:
                left_id = _font_id(left.payload)
                right_id = _font_id(right.payload)
                if left_id is None or left_id != right_id:
                    non_font_changes.append(index)
                else:
                    changed_fonts.append(left_id)
            else:
                non_font_changes.append(index)
    if non_font_changes:
        reasons.append("non-font tags changed")
    wanted = set(character_ids or ())
    if wanted:
        unexpected = sorted(set(changed_fonts) - wanted)
        missing = sorted(wanted - set(changed_fonts))
        if unexpected:
            reasons.append(f"unrequested font IDs changed: {unexpected}")
        if missing:
            reasons.append(f"requested font IDs did not change: {missing}")
    growth = (candidate.stat().st_size - original.stat().st_size) / max(original.stat().st_size, 1)
    large_growth = growth > 0.50
    if large_growth:
        reasons.append(f"candidate grew by {growth:.0%}")
    level = "blocked" if non_font_changes or not tag_count_same or source.payload_header != rebuilt.payload_header or source.magic != rebuilt.magic or large_growth else ("caution" if reasons else "safe")
    return GfxRebuildComparison(
        original_size=original.stat().st_size,
        candidate_size=candidate.stat().st_size,
        changed_font_ids=tuple(sorted(set(changed_fonts))),
        non_font_changes=tuple(non_font_changes),
        tag_count_same=tag_count_same,
        level=level,
        reasons=tuple(reasons),
    )


def assess_gfx_safety(
    gfx_path: str | Path,
    *,
    candidate_path: str | Path | None = None,
    character_ids: set[int] | frozenset[int] | None = None,
) -> GfxSafetyReport:
    """Return a conservative runtime-risk report without writing files."""

    path = Path(gfx_path).expanduser().resolve()
    container = _container_or_error(path)
    font_tags = [tag for tag in container.tags if tag.code == DEFINE_FONT3_TAG]
    reasons: list[str] = []
    if container.compressed and len(container.payload) < 64 * 1024:
        reasons.append("small compressed GFX/CFX with embedded font")
    largest_font = max((len(tag.payload) for tag in font_tags), default=0)
    if largest_font and largest_font / max(len(container.payload), 1) > 0.50:
        reasons.append("font tag occupies most of the payload")
    if len(font_tags) > 2:
        reasons.append("multiple embedded font tags")
    if candidate_path is not None:
        comparison = compare_gfx_rebuilds(path, candidate_path, character_ids)
        reasons.extend(comparison.reasons)
        if comparison.level == "blocked":
            level = "blocked"
        elif comparison.level == "caution" or reasons:
            level = "caution"
        else:
            level = "safe"
    else:
        level = "caution" if reasons else "safe"
    return GfxSafetyReport(
        path=str(path),
        container=container.magic.decode("ascii"),
        file_size=path.stat().st_size,
        payload_size=len(container.payload),
        tag_count=len(container.tags),
        font_tag_count=len(font_tags),
        largest_font_tag_size=largest_font,
        level=level,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def migrate_define_font3_tags(
    original_path: str | Path,
    candidate_path: str | Path,
    output_path: str | Path,
    character_ids: set[int] | frozenset[int],
) -> Path:
    """Transplant selected font tags from a candidate while preserving other tags."""

    source = Path(original_path).expanduser().resolve()
    candidate = Path(candidate_path).expanduser().resolve()
    destination = Path(output_path).expanduser().resolve()
    if source == destination:
        raise ValueError("output GFX must differ from input GFX")
    if not character_ids:
        raise ValueError("at least one DefineFont3 ID is required")
    original_container = _container_or_error(source)
    candidate_container = _container_or_error(candidate)
    payload = replace_define_font3_tags(
        original_container.payload,
        candidate_container.payload,
        character_ids,
        require_non_font_identity=False,
    )
    if original_container.magic != candidate_container.magic:
        raise GfxFormatError("original and candidate container kinds differ")
    from .swf import encode_gfx_container

    encoded = encode_gfx_container(original_container, payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".partial", dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        temporary.write_bytes(encoded)
        _container_or_error(temporary)
        shutil.copy2(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def replace_font_slots_in_place(
    gfx_path: str | Path,
    output_gfx: str | Path,
    replacements: Mapping[int, str | Path],
    *,
    ffdec_cli: str | Path | None = None,
) -> Path:
    """Use FFDec only to create a candidate, then transplant font tags."""

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

    with tempfile.TemporaryDirectory(prefix="cryengine_gfx_candidate_") as temporary_dir:
        current = source
        for character_id, font_file in sorted(replacements.items()):
            candidate = Path(temporary_dir) / f"candidate_{character_id}.gfx"
            command = build_font_replace_command(tool, current, candidate, character_id, font_file)
            try:
                subprocess.run(command, check=True, capture_output=True, text=True)
            except (OSError, subprocess.CalledProcessError) as exc:
                raise GfxToolError(f"FFDec font replacement failed for ID {character_id}: {exc}") from exc
            if not candidate.is_file() or candidate.stat().st_size == 0:
                raise GfxToolError(f"FFDec produced no GFX output for ID {character_id}")
            current = candidate
        return migrate_define_font3_tags(source, current, destination, set(replacements))


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
        raise GfxNoFontSlotsError("FFDec output contained no DefineFont3 slots")
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
    python_executable: str | Path | None = None,
) -> Path:
    """Create a subset font using bundled fontTools or an explicit Python."""

    if python_executable is None:
        return _subset_font_in_process(font_file, text_file, output_file)

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


def _subset_font_in_process(
    font_file: str | Path,
    text_file: str | Path,
    output_file: str | Path,
) -> Path:
    """Run fontTools' subset API inside the current process."""

    try:
        from fontTools import subset as font_subset
    except ImportError as exc:
        raise GfxToolError("bundled fontTools is unavailable; pass --python to use a custom interpreter") from exc
    source = Path(font_file).expanduser().resolve()
    text_path = Path(text_file).expanduser().resolve()
    destination = Path(output_file).expanduser().resolve()
    try:
        characters = "".join(sorted(set(text_path.read_text(encoding="utf-8")) - {"\n", "\r"}))
        options = font_subset.Options()
        options.layout_features = ["*"]
        options.glyph_names = True
        options.symbol_cmap = True
        options.name_IDs = ["*"]
        font = font_subset.load_font(str(source), options)
        subsetter = font_subset.Subsetter(options=options)
        subsetter.populate(text=characters)
        subsetter.subset(font)
        destination.parent.mkdir(parents=True, exist_ok=True)
        font_subset.save_font(font, str(destination), options)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        raise GfxToolError(f"bundled fontTools subset failed: {exc}") from exc
    if not destination.is_file() or destination.stat().st_size == 0:
        raise GfxToolError(f"fontTools produced no output: {destination}")
    return destination


def inspect_font_coverage(
    font_file: str | Path,
    text_file: str | Path,
    *,
    python_executable: str | Path | None = None,
) -> FontCoverage:
    """Report missing characters using bundled fontTools or a custom interpreter."""

    if python_executable is None:
        return _inspect_font_coverage_in_process(font_file, text_file)

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


def _inspect_font_coverage_in_process(font_file: str | Path, text_file: str | Path) -> FontCoverage:
    """Inspect cmap coverage with the bundled fontTools library."""

    try:
        from fontTools.ttLib import TTFont
    except ImportError as exc:
        raise GfxToolError("bundled fontTools is unavailable; pass --python to use a custom interpreter") from exc
    try:
        chars = sorted(set(Path(text_file).expanduser().resolve().read_text(encoding="utf-8")) - {"\n", "\r"})
        font = TTFont(str(Path(font_file).expanduser().resolve()))
        cmap = {codepoint for table in font["cmap"].tables for codepoint in table.cmap}
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise GfxToolError(f"bundled fontTools coverage inspection failed: {exc}") from exc
    missing = tuple(character for character in chars if ord(character) not in cmap)
    return FontCoverage(len(chars), len(chars) - len(missing), missing)


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
    copied only after all FFDec invocations and a GFX/CFX validation succeed.
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
    # FFDec can crash when its output path is deeply nested. Keep every
    # intermediate candidate in the system temporary directory, then copy the
    # verified final result into the caller's requested location.
    with tempfile.TemporaryDirectory(prefix="cryengine_ffdec_") as temporary_dir:
        temporary = Path(temporary_dir)
        current = source
        for character_id, font_file in sorted(replacements.items()):
            stage = temporary / f"slot-{character_id}.gfx"
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
    return destination
