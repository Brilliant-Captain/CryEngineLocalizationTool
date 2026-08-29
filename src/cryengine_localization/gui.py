"""Small Tkinter front-end that delegates all work to the CLI/core."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import Any


def gui_available() -> bool:
    try:
        import tkinter  # noqa: F401

        return True
    except ImportError:
        return False


def build_cli_args(
    source_pak: str,
    csv_file: str,
    output_pak: str,
    manifest: str,
    language: str,
) -> list[str]:
    return [
        "build",
        source_pak,
        csv_file,
        "--output-pak",
        output_pak,
        "--manifest",
        manifest,
        "--language",
        language,
    ]


def launch_gui() -> None:
    """Launch the GUI, raising a clear error when no display is available."""

    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except ImportError as exc:
        raise RuntimeError("Tkinter is unavailable; use the cry-localize CLI") from exc

    from cryengine_localization.cli.main import main as cli_main

    class App:
        def __init__(self, root: Any) -> None:
            self.root = root
            root.title("CryEngine Localization")
            root.geometry("720x360")
            self.fields: dict[str, Any] = {}
            rows = (
                ("Source PAK", "pak", "file", "PAK files", "*.pak"),
                ("Translation CSV", "csv", "file", "CSV files", "*.csv"),
                ("Output PAK", "output", "save", "PAK files", "*.pak"),
                ("Manifest", "manifest", "save", "JSON files", "*.json"),
            )
            for row, (label, key, mode, description, pattern) in enumerate(rows):
                tk.Label(root, text=label, anchor="w", width=18).grid(row=row, column=0, padx=8, pady=8, sticky="w")
                variable = tk.StringVar()
                self.fields[key] = variable
                tk.Entry(root, textvariable=variable, width=64).grid(row=row, column=1, padx=4, sticky="ew")
                command = lambda key=key, mode=mode, description=description, pattern=pattern: self._browse(key, mode, description, pattern)
                tk.Button(root, text="Browse…", command=command).grid(row=row, column=2, padx=8)
            tk.Label(root, text="Language", anchor="w", width=18).grid(row=4, column=0, padx=8, pady=8, sticky="w")
            self.fields["language"] = tk.StringVar(value="zh-CN")
            tk.Entry(root, textvariable=self.fields["language"], width=20).grid(row=4, column=1, padx=4, sticky="w")
            tk.Button(root, text="Dry-run", command=self._dry_run).grid(row=5, column=0, padx=8, pady=14)
            tk.Button(root, text="Build PAK + Manifest", command=self._build).grid(row=5, column=1, padx=8, pady=14, sticky="w")
            self.log = tk.Text(root, height=8, width=90, state="disabled")
            self.log.grid(row=6, column=0, columnspan=3, padx=8, pady=4, sticky="nsew")
            root.columnconfigure(1, weight=1)
            root.rowconfigure(6, weight=1)

        def _browse(self, key: str, mode: str, description: str, pattern: str) -> None:
            options = {"title": description, "filetypes": [(description, pattern), ("All files", "*.*")]}
            selected = filedialog.asksaveasfilename(**options) if mode == "save" else filedialog.askopenfilename(**options)
            if selected:
                self.fields[key].set(selected)

        def _write_log(self, text: str) -> None:
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n")
            self.log.configure(state="disabled")

        def _dry_run(self) -> None:
            csv_file = self.fields["csv"].get()
            if not csv_file:
                messagebox.showerror("Missing CSV", "Select a translation CSV first")
                return
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = cli_main(["apply", csv_file, "--dry-run"])
            self._write_log(output.getvalue() or f"dry-run exit code: {result}")

        def _build(self) -> None:
            values = {key: variable.get() for key, variable in self.fields.items()}
            missing = [key for key in ("pak", "csv", "output", "manifest") if not values[key]]
            if missing:
                messagebox.showerror("Missing input", "Select: " + ", ".join(missing))
                return
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = cli_main(
                    build_cli_args(values["pak"], values["csv"], values["output"], values["manifest"], values["language"])
                )
            self._write_log(output.getvalue() or f"build exit code: {result}")

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise RuntimeError("no graphical display is available; use the cry-localize CLI") from exc
    App(root)
    root.mainloop()

