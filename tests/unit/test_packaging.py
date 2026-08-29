from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_pyinstaller_spec_is_windowed_and_has_no_resource_datas() -> None:
    spec = (ROOT / "packaging" / "CryEngineLocalization.spec").read_text(encoding="utf-8")

    assert "console=False" in spec
    assert "datas=[]" in spec
    assert "gui_entry.py" in spec


def test_release_workflow_builds_executable_only_from_source() -> None:
    workflow = (ROOT / ".github" / "workflows" / "build-windows-exe.yml").read_text(encoding="utf-8")

    assert "pyinstaller" in workflow
    assert "build_exe.ps1" in workflow
    assert "upload-artifact@v4" in workflow
    assert "release/" in workflow
    assert "Get-ChildItem" in workflow
