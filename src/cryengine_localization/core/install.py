"""Guarded installation transactions with hash-verified rollback."""

from __future__ import annotations

import csv
import hashlib
import os
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


class InstallationError(RuntimeError):
    """An installation request is unsafe or could not be completed."""


class GameRunningError(InstallationError):
    """The target game process is still running."""


@dataclass(frozen=True)
class InstallItem:
    source: Path
    destination: str


@dataclass
class InstalledItem:
    source: Path
    destination: Path
    backup_path: Path | None
    backup_sha256: str | None
    installed_sha256: str
    destination_existed: bool


@dataclass
class InstallationRecord:
    game_root: Path
    backup_dir: Path
    items: list[InstalledItem]
    created_at_utc: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_game_not_running(process_names: Iterable[str] = ("WarOfRights.exe", "War of Rights.exe")) -> None:
    """Fail closed if a configured game process is listed by the OS."""

    names = {Path(name).name.casefold() for name in process_names}
    if not names:
        return
    try:
        if os.name == "nt":
            completed = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if completed.returncode != 0:
                raise InstallationError("tasklist failed while checking game process state")
            running = {
                row[0].casefold()
                for row in csv.reader(completed.stdout.splitlines())
                if row
            }
        else:
            completed = subprocess.run(
                ["ps", "-A", "-o", "comm="],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if completed.returncode != 0:
                raise InstallationError("ps failed while checking game process state")
            running = {line.strip().casefold() for line in completed.stdout.splitlines() if line.strip()}
    except (OSError, subprocess.SubprocessError) as exc:
        raise InstallationError(f"unable to verify game process state: {exc}") from exc
    matches = sorted(names & running)
    if matches:
        raise GameRunningError("game process is running: " + ", ".join(matches))


def _safe_destination(game_root: Path, relative_destination: str) -> Path:
    if not relative_destination or Path(relative_destination).is_absolute():
        raise InstallationError("destination must be a relative path inside game root")
    normalized = relative_destination.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if not parts or ".." in parts or ":" in parts[0]:
        raise InstallationError("destination must be a relative path inside game root")
    destination = (game_root / Path(*parts)).resolve()
    try:
        destination.relative_to(game_root)
    except ValueError as exc:
        raise InstallationError("destination is not inside game root") from exc
    return destination


def plan_install(game_root: str | Path, items: Iterable[InstallItem]) -> list[InstalledItem]:
    root = Path(game_root).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    planned: list[InstalledItem] = []
    for item in items:
        source = Path(item.source).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        destination = _safe_destination(root, item.destination)
        if source == destination:
            raise InstallationError("source and destination must differ")
        exists = destination.is_file()
        planned.append(
            InstalledItem(
                source=source,
                destination=destination,
                backup_path=None,
                backup_sha256=_sha256(destination) if exists else None,
                installed_sha256=_sha256(source),
                destination_existed=exists,
            )
        )
    return planned


def install_files(
    game_root: str | Path,
    items: Iterable[InstallItem],
    *,
    backup_dir: str | Path,
    process_names: Iterable[str] = ("WarOfRights.exe", "War of Rights.exe"),
) -> InstallationRecord:
    root = Path(game_root).expanduser().resolve()
    planned = plan_install(root, items)
    ensure_game_not_running(process_names)
    backup_root = Path(backup_dir).expanduser().resolve()
    backup_root.mkdir(parents=True, exist_ok=True)
    record = InstallationRecord(root, backup_root, [], datetime.now(timezone.utc).replace(microsecond=0).isoformat())
    staged: list[Path] = []
    try:
        for planned_item in planned:
            backup_path = None
            if planned_item.destination_existed:
                relative = planned_item.destination.relative_to(root)
                backup_path = backup_root / relative
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(planned_item.destination, backup_path)
                if _sha256(backup_path) != planned_item.backup_sha256:
                    raise InstallationError(f"backup hash mismatch: {backup_path}")
            destination = planned_item.destination
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.name}.", suffix=".install.partial", dir=destination.parent
            )
            os.close(fd)
            temporary = Path(temporary_name)
            staged.append(temporary)
            shutil.copy2(planned_item.source, temporary)
            os.replace(temporary, destination)
            installed_sha256 = _sha256(destination)
            record.items.append(
                InstalledItem(
                    planned_item.source,
                    destination,
                    backup_path,
                    planned_item.backup_sha256,
                    installed_sha256,
                    planned_item.destination_existed,
                )
            )
            if installed_sha256 != planned_item.installed_sha256:
                raise InstallationError(f"installed file hash mismatch: {destination}")
    except Exception:
        for temporary in staged:
            temporary.unlink(missing_ok=True)
        try:
            rollback_install(record)
        except Exception:
            pass
        raise
    return record


def rollback_install(record: InstallationRecord) -> None:
    """Restore every recorded destination and verify backup hashes first."""

    game_root = record.game_root.expanduser().resolve()
    backup_root = record.backup_dir.expanduser().resolve()
    for item in record.items:
        try:
            item.destination.expanduser().resolve().relative_to(game_root)
        except ValueError as exc:
            raise InstallationError(f"record destination is outside game root: {item.destination}") from exc
        if item.backup_path is not None:
            try:
                item.backup_path.expanduser().resolve().relative_to(backup_root)
            except ValueError as exc:
                raise InstallationError(f"record backup is outside backup root: {item.backup_path}") from exc
    for item in record.items:
        if item.backup_path is not None:
            if not item.backup_path.is_file():
                raise InstallationError(f"backup is missing: {item.backup_path}")
            if _sha256(item.backup_path) != item.backup_sha256:
                raise InstallationError(f"backup hash mismatch: {item.backup_path}")
    for item in reversed(record.items):
        if item.backup_path is not None:
            item.destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.backup_path, item.destination)
            if _sha256(item.destination) != item.backup_sha256:
                raise InstallationError(f"restored file hash mismatch: {item.destination}")
        elif not item.destination_existed and item.destination.exists():
            item.destination.unlink()


def record_to_dict(record: InstallationRecord) -> dict[str, object]:
    data = asdict(record)
    data["game_root"] = str(record.game_root)
    data["backup_dir"] = str(record.backup_dir)
    data["items"] = [
        {
            **asdict(item),
            "source": str(item.source),
            "destination": str(item.destination),
            "backup_path": str(item.backup_path) if item.backup_path else None,
        }
        for item in record.items
    ]
    return data


def write_install_record(record: InstallationRecord, path: str | Path) -> Path:
    import json

    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(record_to_dict(record), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


def read_install_record(path: str | Path) -> InstallationRecord:
    import json

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = [
        InstalledItem(
            source=Path(item["source"]),
            destination=Path(item["destination"]),
            backup_path=Path(item["backup_path"]) if item.get("backup_path") else None,
            backup_sha256=item.get("backup_sha256"),
            installed_sha256=item["installed_sha256"],
            destination_existed=bool(item["destination_existed"]),
        )
        for item in data["items"]
    ]
    return InstallationRecord(Path(data["game_root"]), Path(data["backup_dir"]), items, data["created_at_utc"])
