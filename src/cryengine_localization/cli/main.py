"""Command-line entry points for the localization toolkit."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from cryengine_localization import __version__
from cryengine_localization.adapters.cryengine import identify_project
from cryengine_localization.adapters.pak import build_pak, extract_pak, scan_pak
from cryengine_localization.adapters.gfxfont import scan_gfx_fonts
from cryengine_localization.adapters.textures import parse_dds_header, replace_texture_in_pak
from cryengine_localization.adapters.war_of_rights import preview_language_config
from cryengine_localization.core.apply import apply_catalog_to_pak, plan_translation_changes
from cryengine_localization.core.catalog import catalog_from_json_bytes
from cryengine_localization.core.manifest import build_manifest, sha256_file, write_manifest
from cryengine_localization.io.csv_codec import export_catalog, import_catalog


def _catalog_from_pak(path: str | Path):
    archive = scan_pak(path)
    rows = []
    from zipfile import ZipFile

    with ZipFile(archive.path, "r") as source:
        payload = {entry.path: source.read(entry.source_name) for entry in archive.entries}
    for entry in archive.entries:
        if not entry.path.casefold().endswith(".json"):
            continue
        try:
            rows.extend(catalog_from_json_bytes(entry.path, payload[entry.path]))
        except (UnicodeDecodeError, ValueError):
            continue
    return rows


def _cmd_identify(args: argparse.Namespace) -> int:
    info = identify_project(args.path)
    print(
        json.dumps(
            {
                "path": str(info.path),
                "engine": info.engine,
                "confidence": info.confidence,
                "has_cryproject": info.has_cryproject,
                "has_assets": info.has_assets,
                "pak_files": [str(path) for path in info.pak_files],
                "engine_version": info.engine_version,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _cmd_pak_list(args: argparse.Namespace) -> int:
    archive = scan_pak(args.path)
    for entry in archive.entries:
        print(f"{entry.size:>10}  {entry.path}")
    return 0


def _cmd_pak_extract(args: argparse.Namespace) -> int:
    written = extract_pak(args.path, args.output, match=args.match, overwrite=args.overwrite)
    print(f"extracted {len(written)} files to {Path(args.output).resolve()}")
    return 0


def _cmd_pak_build(args: argparse.Namespace) -> int:
    root = Path(args.input).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    entries = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and not path.name.endswith(".partial")
    }
    output = build_pak(entries, args.output)
    print(output)
    return 0


def _cmd_catalog_export(args: argparse.Namespace) -> int:
    entries = _catalog_from_pak(args.path)
    export_catalog(entries, args.output)
    print(f"exported {len(entries)} rows to {Path(args.output).resolve()}")
    return 0


def _cmd_apply(args: argparse.Namespace) -> int:
    entries = import_catalog(args.csv)
    changes = plan_translation_changes(entries)
    if args.dry_run:
        print(
            json.dumps(
                [change.__dict__ for change in changes], ensure_ascii=False, indent=2
            )
        )
        return 0
    if not args.source_pak or not args.output_pak:
        raise ValueError("non-dry-run apply requires --source-pak and --output-pak")
    apply_catalog_to_pak(args.source_pak, entries, args.output_pak)
    print(f"wrote {Path(args.output_pak).resolve()}")
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    entries = import_catalog(args.csv)
    output = Path(args.output_pak).expanduser().resolve()
    source = Path(args.source_pak).expanduser().resolve()
    changes = apply_catalog_to_pak(str(source), entries, str(output))
    replacements = [
        {
            "source_path": change.source_path,
            "text_key": change.text_key,
            "translation_sha256": hashlib.sha256(change.translation.encode("utf-8")).hexdigest(),
        }
        for change in changes
    ]
    manifest = build_manifest(
        tool_version=__version__,
        engine_version=args.engine_version,
        target_language=args.language,
        source_packages=[{"path": source.name, "sha256": sha256_file(source)}],
        replacements=replacements,
        font_strategy={"mode": args.font_mode, "character_ids": args.font_character_id},
        output_sha256=sha256_file(output),
        project=args.project,
    )
    write_manifest(manifest, args.manifest)
    print(f"wrote {output}")
    print(f"manifest {Path(args.manifest).expanduser().resolve()}")
    return 0


def _cmd_font_scan(args: argparse.Namespace) -> int:
    slots = scan_gfx_fonts(args.gfx, args.ffdec)
    print(json.dumps([slot.__dict__ for slot in slots], ensure_ascii=False, indent=2))
    return 0


def _cmd_texture_inspect(args: argparse.Namespace) -> int:
    metadata = parse_dds_header(Path(args.dds).read_bytes())
    print(json.dumps(metadata.__dict__, ensure_ascii=False, indent=2))
    return 0


def _cmd_texture_replace(args: argparse.Namespace) -> int:
    output = replace_texture_in_pak(
        args.source_pak,
        args.entry,
        args.replacement,
        args.output_pak,
        require_alpha=args.require_alpha,
    )
    print(output)
    return 0


def _cmd_config_preview(args: argparse.Namespace) -> int:
    text = Path(args.config).read_text(encoding="utf-8")
    preview = preview_language_config(text, args.language)
    print(json.dumps({"after": preview.after, "diff": list(preview.diff)}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cry-localize", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    identify = sub.add_parser("identify", help="identify a CryEngine project")
    identify.add_argument("path")
    identify.set_defaults(func=_cmd_identify)

    pak = sub.add_parser("pak", help="inspect or build a PAK")
    pak_sub = pak.add_subparsers(dest="pak_command", required=True)
    pak_list = pak_sub.add_parser("list")
    pak_list.add_argument("path")
    pak_list.set_defaults(func=_cmd_pak_list)
    pak_extract = pak_sub.add_parser("extract")
    pak_extract.add_argument("path")
    pak_extract.add_argument("output")
    pak_extract.add_argument("--match")
    pak_extract.add_argument("--overwrite", action="store_true")
    pak_extract.set_defaults(func=_cmd_pak_extract)
    pak_build = pak_sub.add_parser("build")
    pak_build.add_argument("input")
    pak_build.add_argument("output")
    pak_build.set_defaults(func=_cmd_pak_build)

    catalog = sub.add_parser("catalog", help="export a translation catalog")
    catalog_sub = catalog.add_subparsers(dest="catalog_command", required=True)
    catalog_export = catalog_sub.add_parser("export")
    catalog_export.add_argument("path")
    catalog_export.add_argument("--output", required=True)
    catalog_export.set_defaults(func=_cmd_catalog_export)

    apply = sub.add_parser("apply", help="preview or apply a translation table")
    apply.add_argument("csv")
    apply.add_argument("--dry-run", action="store_true")
    apply.add_argument("--source-pak")
    apply.add_argument("--output-pak")
    apply.set_defaults(func=_cmd_apply)

    build = sub.add_parser("build", help="apply translations and write a PAK plus manifest")
    build.add_argument("source_pak")
    build.add_argument("csv")
    build.add_argument("--output-pak", required=True)
    build.add_argument("--manifest", required=True)
    build.add_argument("--language", default="zh-CN")
    build.add_argument("--engine-version")
    build.add_argument("--project")
    build.add_argument("--font-mode", choices=("none", "full", "subset"), default="none")
    build.add_argument("--font-character-id", action="append", type=int, default=[])
    build.set_defaults(func=_cmd_build)

    font = sub.add_parser("font", help="inspect GFX fonts")
    font_sub = font.add_subparsers(dest="font_command", required=True)
    font_scan = font_sub.add_parser("scan")
    font_scan.add_argument("gfx")
    font_scan.add_argument("--ffdec", required=True)
    font_scan.set_defaults(func=_cmd_font_scan)

    texture = sub.add_parser("texture", help="inspect or replace DDS textures")
    texture_sub = texture.add_subparsers(dest="texture_command", required=True)
    texture_inspect = texture_sub.add_parser("inspect")
    texture_inspect.add_argument("dds")
    texture_inspect.set_defaults(func=_cmd_texture_inspect)
    texture_replace = texture_sub.add_parser("replace")
    texture_replace.add_argument("source_pak")
    texture_replace.add_argument("entry")
    texture_replace.add_argument("replacement")
    texture_replace.add_argument("--output-pak", required=True)
    texture_replace.add_argument("--require-alpha", action="store_true")
    texture_replace.set_defaults(func=_cmd_texture_replace)

    config = sub.add_parser("config", help="preview game configuration changes")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_preview = config_sub.add_parser("preview")
    config_preview.add_argument("config")
    config_preview.add_argument("--language", default="english")
    config_preview.set_defaults(func=_cmd_config_preview)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
