from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_public_tree_excludes_internal_session_artifacts() -> None:
    assert not (ROOT / "EXECUTION_CHECKLIST.md").exists()
    assert not list((ROOT / "docs" / "plans").glob("*.md"))
    assert not (ROOT / "docs" / "github-release-checklist.md").exists()

    documents = [*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md")]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in documents)
    forbidden = (
        "For " + "Claude",
        "REQUIRED SUB" + "-SKILL",
        "新窗口" + "第一条动作",
        "当前对话" + "上下文",
        "WoR_CN" + "_Work",
        "_codex" + "_test_cleanup",
        "G:" + "\\tool\\CryEngine",
        "外部操作" + "说明文件",
        "release" + "\\操作教程.md",
    )
    assert not [text for text in forbidden if text in combined]


def test_package_versions_match() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package = (ROOT / "src" / "cryengine_localization" / "__init__.py").read_text(encoding="utf-8")

    assert 'version = "0.6.2"' in pyproject
    assert '__version__ = "0.6.2"' in package
