"""External tool discovery with explicit, serializable diagnostics."""

from __future__ import annotations

import shutil
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ToolInfo:
    name: str
    path: str | None
    version: str | None
    available: bool
    detail: str | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def probe_command(
    name: str,
    candidates: Iterable[str | Path] = (),
    version_args: tuple[str, ...] = ("--version",),
) -> ToolInfo:
    paths: list[str] = [str(candidate) for candidate in candidates]
    resolved = shutil.which(name)
    if resolved:
        paths.append(resolved)
    for candidate in paths:
        try:
            completed = subprocess.run(
                [candidate, *version_args],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        output = (completed.stdout or completed.stderr).strip().splitlines()
        if output or completed.returncode == 0:
            return ToolInfo(name, str(Path(candidate).resolve()), output[0] if output else None, True)
    return ToolInfo(name, None, None, False, "not found or not executable")


def probe_python_module(executable: str | Path, module: str) -> ToolInfo:
    path = str(executable)
    try:
        completed = subprocess.run(
            [path, "-c", f"import {module}; print(getattr({module}, '__version__', 'available'))"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ToolInfo(module, path, None, False, str(exc))
    output = (completed.stdout or completed.stderr).strip().splitlines()
    return ToolInfo(module, str(Path(path).resolve()), output[0] if output else "available", True)


def _python_candidates() -> tuple[str, ...]:
    candidates = [sys.executable]
    for name in ("python", "python3", "py"):
        resolved = shutil.which(name)
        if resolved and resolved not in candidates:
            candidates.append(resolved)
    return tuple(candidates)


def discover_tools(*, ffdec: str | Path | None = None) -> dict[str, ToolInfo]:
    """Probe tools used by the adapters without installing anything."""

    python_path = _python_candidates()[0]
    ffdec_candidates = (ffdec,) if ffdec else tuple(
        candidate
        for candidate in (
            os.environ.get("FFDEC_CLI"),
            shutil.which("ffdec-cli"),
            shutil.which("ffdec"),
        )
        if candidate
    )
    report = {
        "python": probe_command("python", _python_candidates(), ("--version",)),
        "git": probe_command("git"),
        "ffmpeg": probe_command("ffmpeg"),
        "texconv": probe_command("texconv"),
        "compressonator": probe_command("compressonatorcli"),
        "ffdec": probe_command("ffdec", ffdec_candidates),
        "fontTools": probe_python_module(python_path, "fontTools"),
        "Pillow": probe_python_module(python_path, "PIL"),
        "pytest": probe_python_module(python_path, "pytest"),
    }
    # If the first Python lacks fontTools/Pillow, inspect the other discovered
    # interpreters and keep the first interpreter that provides each module.
    for candidate in _python_candidates()[1:]:
        for key, module in (("fontTools", "fontTools"), ("Pillow", "PIL"), ("pytest", "pytest")):
            if not report[key].available:
                alternate = probe_python_module(candidate, module)
                if alternate.available:
                    report[key] = alternate
    return report
