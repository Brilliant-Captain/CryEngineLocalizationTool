"""Pure helpers used by the Tkinter GUI and easy to exercise in tests."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from cryengine_localization.core.profile import BatchProfile, FontProfile, FontSlot, InstallFile, InstallProfile, ProjectProfile


def build_cli_args(
    source_pak: str,
    csv_file: str,
    output_pak: str,
    manifest: str,
    language: str,
    *,
    project: str | None = None,
    overlay_mode: str = "standalone",
    engine_version: str | None = None,
) -> list[str]:
    """Build generic translation build arguments without game-specific defaults."""

    args = [
        "build",
        source_pak,
        csv_file,
        "--output-pak",
        output_pak,
        "--manifest",
        manifest,
        "--language",
        language,
        "--overlay-mode",
        overlay_mode,
    ]
    if engine_version:
        args.extend(["--engine-version", engine_version])
    if project:
        args.extend(["--project", project])
    return args


def build_catalog_export_args(source_pak: str, csv_file: str) -> list[str]:
    return ["catalog", "export", source_pak, "--output", csv_file]


def confirm_csv_overwrite(path: str | Path, confirm: Callable[[str], bool]) -> bool:
    """Return whether an export may write to ``path``."""

    destination = Path(path).expanduser()
    return not destination.exists() or bool(confirm(str(destination)))


def _join_lines(values: tuple[str, ...]) -> str:
    return "\n".join(values)


def profile_to_form(profile: ProjectProfile) -> dict[str, str]:
    """Convert a profile into string values suitable for Tkinter variables."""

    return {
        "name": profile.name,
        "engine_version": profile.engine_version or "",
        "source_pak": profile.source_pak,
        "translation_csv": profile.translation_csv,
        "output_pak": profile.output_pak,
        "manifest": profile.manifest,
        "language": profile.language,
        "ui_language": profile.ui_language,
        "overlay_mode": profile.overlay_mode,
        "font_enabled": "true" if profile.font.enabled else "false",
        "font_source_gfx": profile.font.source_gfx,
        "font_output_gfx": profile.font.output_gfx,
        "font_ffdec": profile.font.ffdec,
        "font_python": profile.font.python,
        "font_output_pak": profile.font.output_pak,
        "font_coverage_font": profile.font.coverage_font,
        "font_coverage_text": profile.font.coverage_text,
        "font_subset_output_font": profile.font.subset_output_font,
        "font_slots": ";".join(f"{slot.character_id}={slot.font_file}" for slot in profile.font.slots),
        "batch_enabled": "true" if profile.batch.enabled else "false",
        "batch_game_root": profile.batch.game_root,
        "batch_catalog_csv": profile.batch.catalog_csv,
        "batch_legacy_translation_csv": profile.batch.legacy_translation_csv,
        "batch_scan_report": profile.batch.scan_report,
        "batch_translation_overlay_pak": profile.batch.translation_overlay_pak,
        "batch_manifest": profile.batch.manifest,
        "batch_font_file": profile.batch.font_file,
        "batch_font_overlay_pak": profile.batch.font_overlay_pak,
        "batch_ffdec": profile.batch.ffdec,
        "install_game_root": profile.install.game_root,
        "install_backup_dir": profile.install.backup_dir,
        "install_record": profile.install.record,
        "install_files": _join_lines(tuple(f"{item.source}={item.destination}" for item in profile.install.files)),
        "install_process_names": _join_lines(profile.install.process_names),
    }


def _parse_slots(value: str) -> tuple[FontSlot, ...]:
    slots: list[FontSlot] = []
    for item in value.split(";"):
        item = item.strip()
        if not item:
            continue
        identifier, separator, font_file = item.partition("=")
        if not separator or not identifier.strip().isdigit() or not font_file.strip():
            raise ValueError(f"invalid font slot {item!r}; expected ID=FONT_FILE")
        slots.append(FontSlot(int(identifier.strip()), font_file.strip()))
    return tuple(slots)


def _parse_install_files(value: str) -> tuple[InstallFile, ...]:
    files: list[InstallFile] = []
    for line in value.replace(";", "\n").splitlines():
        line = line.strip()
        if not line:
            continue
        source, separator, destination = line.partition("=")
        if not separator or not source.strip() or not destination.strip():
            raise ValueError(f"invalid install file {line!r}; expected SOURCE=GAME_RELATIVE_PATH")
        files.append(InstallFile(source.strip(), destination.strip()))
    return tuple(files)


def profile_from_form(values: dict[str, str]) -> ProjectProfile:
    """Build and validate a project profile from GUI form values."""

    enabled = values.get("font_enabled", "false").strip().casefold() in {"1", "true", "yes", "on"}
    batch_enabled = values.get("batch_enabled", "false").strip().casefold() in {"1", "true", "yes", "on"}
    profile = ProjectProfile(
        name=values.get("name", ""),
        engine_version=values.get("engine_version", "") or None,
        source_pak=values.get("source_pak", ""),
        translation_csv=values.get("translation_csv", ""),
        output_pak=values.get("output_pak", ""),
        manifest=values.get("manifest", ""),
        language=values.get("language", "zh-CN"),
        ui_language=values.get("ui_language", "zh-CN"),
        overlay_mode=values.get("overlay_mode", "standalone"),
        font=FontProfile(
            enabled=enabled,
            source_gfx=values.get("font_source_gfx", ""),
            output_gfx=values.get("font_output_gfx", ""),
            ffdec=values.get("font_ffdec", ""),
            python=values.get("font_python", ""),
            output_pak=values.get("font_output_pak", ""),
            coverage_font=values.get("font_coverage_font", ""),
            coverage_text=values.get("font_coverage_text", ""),
            subset_output_font=values.get("font_subset_output_font", ""),
            slots=_parse_slots(values.get("font_slots", "")),
        ),
        batch=BatchProfile(
            enabled=batch_enabled,
            game_root=values.get("batch_game_root", ""),
            catalog_csv=values.get("batch_catalog_csv", ""),
            legacy_translation_csv=values.get("batch_legacy_translation_csv", ""),
            scan_report=values.get("batch_scan_report", ""),
            translation_overlay_pak=values.get("batch_translation_overlay_pak", ""),
            manifest=values.get("batch_manifest", ""),
            font_file=values.get("batch_font_file", ""),
            font_overlay_pak=values.get("batch_font_overlay_pak", ""),
            ffdec=values.get("batch_ffdec", ""),
        ),
        install=InstallProfile(
            game_root=values.get("install_game_root", ""),
            backup_dir=values.get("install_backup_dir", ""),
            record=values.get("install_record", ""),
            files=_parse_install_files(values.get("install_files", "")),
            process_names=tuple(line.strip() for line in values.get("install_process_names", "").splitlines() if line.strip()),
        ),
    )
    return profile.validate()
