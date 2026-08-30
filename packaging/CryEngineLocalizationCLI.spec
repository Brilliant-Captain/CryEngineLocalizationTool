# PyInstaller one-file, console build for the generic CLI.
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPEC).resolve().parents[1]

a = Analysis(
    [str(project_root / "scripts" / "cli_entry.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=[(str(project_root / "src" / "cryengine_localization" / "locales"), "cryengine_localization/locales")],
    hiddenimports=["tkinter", "tkinter.filedialog", "tkinter.messagebox", *collect_submodules("fontTools")],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="cry-localize",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)
