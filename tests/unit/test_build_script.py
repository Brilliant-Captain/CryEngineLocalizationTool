from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_build_script_writes_basename_only_checksum() -> None:
    script = (ROOT / "scripts" / "build_exe.ps1").read_text(encoding="utf-8")

    assert "Split-Path -Leaf" in script
    assert "SHA256SUMS.json" in script
    assert "CryEngineLocalizationCLI.spec" in script
    assert "cry-localize.exe" in script
    assert "fontTools" in script
