"""PyInstaller entry point for the windowed GUI executable."""

from __future__ import annotations


def main() -> int:
    try:
        from cryengine_localization.gui import launch_gui

        launch_gui()
        return 0
    except Exception as exc:  # pragma: no cover - exercised by the packaged app
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("CryEngine Localization", str(exc))
            root.destroy()
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

