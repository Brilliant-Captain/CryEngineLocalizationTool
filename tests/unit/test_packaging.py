from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_pyinstaller_spec_is_windowed_and_packages_locale_resources() -> None:
    spec = (ROOT / "packaging" / "CryEngineLocalization.spec").read_text(encoding="utf-8")

    assert "console=False" in spec
    assert "locales" in spec
    assert "gui_entry.py" in spec


def test_console_entry_and_spec_share_the_same_cli() -> None:
    entry = (ROOT / "scripts" / "cli_entry.py").read_text(encoding="utf-8")
    spec = (ROOT / "packaging" / "CryEngineLocalizationCLI.spec").read_text(encoding="utf-8")

    assert "cryengine_localization.cli.main" in entry
    assert "cli_entry.py" in spec
    assert "console=True" in spec
    assert "locales" in spec
    assert "tkinter" in spec
    assert "fontTools" in spec


def test_release_workflow_builds_executable_only_from_source() -> None:
    workflow = (ROOT / ".github" / "workflows" / "build-windows-exe.yml").read_text(encoding="utf-8")

    assert "pyinstaller" in workflow
    assert "build_exe.ps1" in workflow
    assert "upload-artifact@v4" in workflow
    assert "release/" in workflow
    assert "Get-ChildItem" in workflow
