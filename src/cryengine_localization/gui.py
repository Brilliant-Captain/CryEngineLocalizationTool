"""Tkinter workbench for the generic CryEngine localization workflow."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from cryengine_localization.adapters.gfxfont import inspect_font_coverage, replace_font_slots, scan_gfx_fonts, subset_font
from cryengine_localization.adapters.pak import build_pak, extract_pak, scan_pak
from cryengine_localization.core.install import InstalledItem
from cryengine_localization.core.profile import ProjectProfile, load_profile, save_profile
from cryengine_localization.core.workflow import (
    build_profile,
    export_profile_catalog,
    install_profile,
    plan_profile_changes,
    plan_profile_install,
    rollback_profile,
)
from cryengine_localization.i18n import LocaleCatalog, available_locales, load_locale
from cryengine_localization.gui_model import (
    build_cli_args,
    confirm_csv_overwrite,
    profile_from_form,
    profile_to_form,
)


def gui_available() -> bool:
    try:
        import tkinter  # noqa: F401

        return True
    except ImportError:
        return False


def launch_gui(ui_language: str | None = None) -> None:
    """Launch the generic GUI, raising a clear error without a display."""

    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as exc:
        raise RuntimeError("Tkinter is unavailable; use the cry-localize CLI") from exc

    class App:
        def __init__(self, root: Any) -> None:
            self.root = root
            try:
                self.locale_catalog: LocaleCatalog = load_locale(ui_language or "zh-CN")
            except Exception:
                self.locale_catalog = load_locale("en-US")
            self._localized_widgets: list[tuple[Any, str]] = []
            self._localized_tabs: list[tuple[Any, Any, str]] = []
            root.geometry("1080x760")
            root.minsize(900, 620)
            self.fields: dict[str, Any] = {}
            self.profile_path = tk.StringVar()
            self.ui_language = tk.StringVar(value=self.locale_catalog.locale)
            root.title(self._t("app.title"))
            self._build_header(root, ttk, filedialog, messagebox)

            notebook = ttk.Notebook(root)
            notebook.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 4))
            self._build_project_tab(notebook, ttk, filedialog)
            self._build_translation_tab(notebook, ttk, messagebox)
            self._build_font_tab(notebook, ttk, filedialog)
            self._build_pak_tab(notebook, ttk, filedialog)
            self._build_install_tab(notebook, ttk, messagebox)

            log_frame = ttk.LabelFrame(root)
            self._localized(log_frame, "label.log")
            log_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(4, 8))
            self.log = tk.Text(log_frame, height=9, width=120, state="disabled", wrap="none")
            self.log.grid(row=0, column=0, sticky="nsew")
            scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
            scrollbar.grid(row=0, column=1, sticky="ns")
            self.log.configure(yscrollcommand=scrollbar.set)
            log_frame.columnconfigure(0, weight=1)
            log_frame.rowconfigure(0, weight=1)
            root.columnconfigure(0, weight=1)
            root.rowconfigure(1, weight=1)
            root.rowconfigure(2, weight=1)
            self._set_profile(ProjectProfile())

        def _build_header(self, root: Any, ttk: Any, filedialog: Any, messagebox: Any) -> None:
            header = ttk.Frame(root)
            header.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
            self._localized(ttk.Label(header), "header.profile").grid(row=0, column=0, padx=(0, 6))
            ttk.Entry(header, textvariable=self.profile_path, width=76).grid(row=0, column=1, sticky="ew")
            self._localized(ttk.Button(header, command=self._new_profile), "button.new").grid(row=0, column=2, padx=4)
            self._localized(ttk.Button(header, command=lambda: self._open_profile(filedialog)), "button.open").grid(row=0, column=3, padx=4)
            self._localized(ttk.Button(header, command=lambda: self._save_profile(filedialog)), "button.save").grid(row=0, column=4, padx=4)
            self._localized(ttk.Label(header), "header.ui_language").grid(row=0, column=5, padx=(18, 6))
            locale_values = tuple(available_locales())
            locale_box = ttk.Combobox(header, textvariable=self.ui_language, state="readonly", values=locale_values, width=12)
            locale_box.grid(row=0, column=6, padx=4)
            locale_box.bind("<<ComboboxSelected>>", self._on_locale_changed)
            header.columnconfigure(1, weight=1)

        def _build_project_tab(self, notebook: Any, ttk: Any, filedialog: Any) -> None:
            tab = ttk.Frame(notebook, padding=12)
            self._localized_tab(notebook, tab, "tab.project")
            self._add_entry(tab, ttk, 0, "field.project_name", "name")
            self._add_entry(tab, ttk, 1, "field.engine_version", "engine_version")
            self._add_path_entry(tab, ttk, filedialog, 2, "field.source_pak", "source_pak", save=False, pattern="*.pak")
            self._add_path_entry(tab, ttk, filedialog, 3, "field.translation_csv", "translation_csv", save=True, pattern="*.csv")
            self._add_path_entry(tab, ttk, filedialog, 4, "field.output_translation_pak", "output_pak", save=True, pattern="*.pak")
            self._add_path_entry(tab, ttk, filedialog, 5, "field.manifest", "manifest", save=True, pattern="*.json")
            self._add_entry(tab, ttk, 6, "field.language", "language", default="zh-CN")
            self._localized(ttk.Label(tab), "field.overlay_mode").grid(row=7, column=0, sticky="w", pady=5)
            ttk.Combobox(tab, textvariable=self._var("overlay_mode"), state="readonly", values=("standalone", "english-path-overlay"), width=28).grid(row=7, column=1, sticky="w", pady=5)
            self._localized(ttk.Label(tab, foreground="#555555"), "hint.no_auto_select").grid(row=8, column=0, columnspan=3, sticky="w", pady=(14, 4))
            tab.columnconfigure(1, weight=1)

        def _build_translation_tab(self, notebook: Any, ttk: Any, messagebox: Any) -> None:
            tab = ttk.Frame(notebook, padding=12)
            self._localized_tab(notebook, tab, "tab.translation")
            self._localized(ttk.Label(tab, foreground="#555555"), "hint.export_read_only").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
            self._localized(ttk.Button(tab, command=lambda: self._export_csv(messagebox)), "button.export_csv").grid(row=1, column=0, padx=(0, 8), pady=4, sticky="w")
            self._localized(ttk.Button(tab, command=self._dry_run), "button.dry_run").grid(row=1, column=1, padx=8, pady=4, sticky="w")
            self._localized(ttk.Button(tab, command=self._build_translation), "button.build_translation").grid(row=1, column=2, padx=8, pady=4, sticky="w")
            tab.columnconfigure(2, weight=1)

        def _build_font_tab(self, notebook: Any, ttk: Any, filedialog: Any) -> None:
            tab = ttk.Frame(notebook, padding=12)
            self._localized_tab(notebook, tab, "tab.fonts")
            self._localized(ttk.Checkbutton(tab, variable=self._var("font_enabled"), onvalue="true", offvalue="false"), "check.enable_font").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
            self._add_path_entry(tab, ttk, filedialog, 1, "field.source_gfx", "font_source_gfx", save=False, pattern="*.gfx")
            self._add_path_entry(tab, ttk, filedialog, 2, "field.output_gfx", "font_output_gfx", save=True, pattern="*.gfx")
            self._add_path_entry(tab, ttk, filedialog, 3, "field.ffdec", "font_ffdec", save=False, pattern="*.exe")
            self._add_path_entry(tab, ttk, filedialog, 4, "field.font_python", "font_python", save=False, pattern="*.exe")
            self._add_path_entry(tab, ttk, filedialog, 5, "field.coverage_font", "font_coverage_font", save=False, pattern="*.ttf")
            self._add_path_entry(tab, ttk, filedialog, 6, "field.coverage_text", "font_coverage_text", save=False, pattern="*.txt")
            self._add_path_entry(tab, ttk, filedialog, 7, "field.subset_output_font", "font_subset_output_font", save=True, pattern="*.ttf")
            self._add_path_entry(tab, ttk, filedialog, 8, "field.output_font_pak", "font_output_pak", save=True, pattern="*.pak")
            self._add_entry(tab, ttk, 9, "field.font_slots", "font_slots")
            self._localized(ttk.Label(tab, foreground="#555555"), "hint.font_slots").grid(row=10, column=1, columnspan=2, sticky="w", pady=(0, 8))
            self._localized(ttk.Button(tab, command=self._scan_fonts), "button.scan_gfx").grid(row=11, column=0, padx=(0, 8), pady=4, sticky="w")
            self._localized(ttk.Button(tab, command=self._font_coverage), "button.coverage").grid(row=11, column=1, padx=8, pady=4, sticky="w")
            self._localized(ttk.Button(tab, command=self._create_subset), "button.create_subset").grid(row=11, column=2, padx=8, pady=4, sticky="w")
            self._localized(ttk.Button(tab, command=self._replace_fonts), "button.replace_slots").grid(row=12, column=0, padx=(0, 8), pady=4, sticky="w")
            self._localized(ttk.Button(tab, command=self._build_font_pak), "button.build_font_pak").grid(row=12, column=1, padx=8, pady=4, sticky="w")
            tab.columnconfigure(1, weight=1)

        def _build_pak_tab(self, notebook: Any, ttk: Any, filedialog: Any) -> None:
            tab = ttk.Frame(notebook, padding=12)
            self._localized_tab(notebook, tab, "tab.pak")
            self._localized(ttk.Button(tab, command=self._list_pak), "button.list_source_pak").grid(row=0, column=0, padx=(0, 8), pady=4, sticky="w")
            self._add_path_entry(tab, ttk, filedialog, 1, "field.extract_destination", "pak_extract_dir", save=False, directory=True)
            self._add_entry(tab, ttk, 2, "field.extract_match", "pak_extract_match")
            self._localized(ttk.Button(tab, command=self._extract_pak), "button.extract").grid(row=3, column=0, padx=(0, 8), pady=4, sticky="w")
            tab.columnconfigure(1, weight=1)

        def _build_install_tab(self, notebook: Any, ttk: Any, messagebox: Any) -> None:
            tab = ttk.Frame(notebook, padding=12)
            self._localized_tab(notebook, tab, "tab.install")
            self._add_entry(tab, ttk, 0, "field.project_root", "install_game_root")
            self._add_entry(tab, ttk, 1, "field.backup_dir", "install_backup_dir")
            self._add_entry(tab, ttk, 2, "field.install_record", "install_record")
            self._add_entry(tab, ttk, 3, "field.install_files", "install_files")
            self._add_entry(tab, ttk, 4, "field.process_names", "install_process_names")
            self._localized(ttk.Label(tab, foreground="#555555"), "hint.install_relative").grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 10))
            self._localized(ttk.Button(tab, command=self._install_dry_run), "button.install_dry_run").grid(row=6, column=0, padx=(0, 8), pady=4, sticky="w")
            self._localized(ttk.Button(tab, command=lambda: self._install(messagebox)), "button.install").grid(row=6, column=1, padx=8, pady=4, sticky="w")
            self._localized(ttk.Button(tab, command=lambda: self._rollback(messagebox)), "button.rollback").grid(row=6, column=2, padx=8, pady=4, sticky="w")
            tab.columnconfigure(1, weight=1)

        def _var(self, key: str) -> Any:
            if key == "ui_language":
                return self.ui_language
            if key not in self.fields:
                import tkinter as tk

                self.fields[key] = tk.StringVar()
            return self.fields[key]

        def _t(self, key: str, **values: object) -> str:
            return self.locale_catalog.get(key, **values)

        def _localized(self, widget: Any, key: str) -> Any:
            widget.configure(text=self._t(key))
            self._localized_widgets.append((widget, key))
            return widget

        def _localized_tab(self, notebook: Any, tab: Any, key: str) -> None:
            notebook.add(tab, text=self._t(key))
            self._localized_tabs.append((notebook, tab, key))

        def _on_locale_changed(self, _event: Any = None) -> None:
            selected = self.ui_language.get().strip()
            try:
                self.locale_catalog = load_locale(selected)
            except Exception as exc:
                self._write_log(self._t("log.error", message=str(exc)))
                self.ui_language.set(self.locale_catalog.locale)
                return
            self.root.title(self._t("app.title"))
            for widget, key in self._localized_widgets:
                try:
                    widget.configure(text=self._t(key))
                except Exception:
                    pass
            for notebook, tab, key in self._localized_tabs:
                notebook.tab(tab, text=self._t(key))

        def _add_entry(self, parent: Any, ttk: Any, row: int, label: str, key: str, *, default: str | None = None) -> None:
            self._localized(ttk.Label(parent), label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=5)
            variable = self._var(key)
            if default is not None:
                variable.set(default)
            ttk.Entry(parent, textvariable=variable, width=80).grid(row=row, column=1, columnspan=2, sticky="ew", pady=5)

        def _add_path_entry(
            self,
            parent: Any,
            ttk: Any,
            filedialog: Any,
            row: int,
            label: str,
            key: str,
            *,
            save: bool,
            pattern: str = "*.*",
            directory: bool = False,
        ) -> None:
            self._localized(ttk.Label(parent), label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=5)
            ttk.Entry(parent, textvariable=self._var(key), width=70).grid(row=row, column=1, sticky="ew", pady=5)

            def browse() -> None:
                if directory:
                    selected = filedialog.askdirectory(title=self._t(label))
                elif save:
                    selected = filedialog.asksaveasfilename(title=self._t(label), filetypes=[(pattern, pattern), ("All files", "*.*")])
                else:
                    selected = filedialog.askopenfilename(title=self._t(label), filetypes=[(pattern, pattern), ("All files", "*.*")])
                if selected:
                    self._var(key).set(selected)

            self._localized(ttk.Button(parent, command=browse), "button.browse").grid(row=row, column=2, padx=(8, 0), pady=5)

        def _values(self) -> dict[str, str]:
            return {key: variable.get() for key, variable in self.fields.items()}

        def _profile(self) -> ProjectProfile:
            return profile_from_form(self._values())

        def _set_profile(self, profile: ProjectProfile) -> None:
            values = profile_to_form(profile)
            for key, value in values.items():
                self._var(key).set(value)
            selected = values.get("ui_language", "zh-CN")
            if selected != self.locale_catalog.locale:
                self._on_locale_changed()

        def _new_profile(self) -> None:
            self.profile_path.set("")
            self._set_profile(ProjectProfile())
            self._write_log(self._t("log.new_profile"))

        def _open_profile(self, filedialog: Any) -> None:
            path = filedialog.askopenfilename(title=self._t("button.open"), filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
            if not path:
                return
            try:
                profile = load_profile(path, validate=False)
                self.profile_path.set(path)
                self._set_profile(profile)
                self._write_log(self._t("log.loaded", path=Path(path).resolve()))
            except Exception as exc:
                self._show_error("error.open_profile", exc)

        def _save_profile(self, filedialog: Any) -> None:
            try:
                profile = self._profile()
                path = self.profile_path.get().strip()
                if not path:
                    path = filedialog.asksaveasfilename(title=self._t("button.save"), defaultextension=".json", filetypes=[("JSON files", "*.json")])
                if not path:
                    return
                saved = save_profile(profile, path)
                self.profile_path.set(str(saved))
                self._write_log(self._t("log.saved", path=saved))
            except Exception as exc:
                self._show_error("error.save_profile", exc)

        def _export_csv(self, messagebox: Any) -> None:
            try:
                profile = self._profile()
                output = Path(profile.translation_csv).expanduser()
                confirmed = confirm_csv_overwrite(output, lambda path: messagebox.askyesno(self._t("confirm.overwrite.title"), self._t("confirm.overwrite.body", path=path)))
                if not confirmed:
                    self._write_log(self._t("log.csv_cancelled"))
                    return
                path, count = export_profile_catalog(profile, overwrite=True)
                self._write_log(self._t("log.exported", count=count, path=path))
            except Exception as exc:
                self._show_error("error.export_csv", exc)

        def _dry_run(self) -> None:
            try:
                changes = plan_profile_changes(self._profile())
                self._write_log(json.dumps([change.__dict__ for change in changes], ensure_ascii=False, indent=2))
            except Exception as exc:
                self._show_error("error.dry_run", exc)

        def _build_translation(self) -> None:
            try:
                output, manifest, changes = build_profile(self._profile())
                self._write_log(
                    f"{self._t('log.wrote', path=output)}\n"
                    f"{self._t('log.manifest', path=manifest)}\n"
                    f"{self._t('log.replacements', count=len(changes))}"
                )
            except Exception as exc:
                self._show_error("error.build_translation", exc)

        def _scan_fonts(self) -> None:
            try:
                profile = self._profile()
                slots = scan_gfx_fonts(profile.font.source_gfx, profile.font.ffdec or None)
                self._write_log(json.dumps([slot.__dict__ for slot in slots], ensure_ascii=False, indent=2))
            except Exception as exc:
                self._show_error("error.scan_gfx", exc)

        def _font_coverage(self) -> None:
            try:
                profile = self._profile()
                if not profile.font.coverage_font or not profile.font.coverage_text:
                    raise ValueError("coverage font and character set file are required")
                coverage = inspect_font_coverage(
                    profile.font.coverage_font,
                    profile.font.coverage_text,
                    python_executable=profile.font.python or None,
                )
                self._write_log(json.dumps(coverage.__dict__, ensure_ascii=False, indent=2))
            except Exception as exc:
                self._show_error("error.font_coverage", exc)

        def _create_subset(self) -> None:
            try:
                profile = self._profile()
                if not profile.font.coverage_font or not profile.font.coverage_text or not profile.font.subset_output_font:
                    raise ValueError("coverage font, character set file, and subset output font are required")
                output = subset_font(
                    profile.font.coverage_font,
                    profile.font.coverage_text,
                    profile.font.subset_output_font,
                    python_executable=profile.font.python or None,
                )
                self._write_log(self._t("log.wrote", path=output))
            except Exception as exc:
                self._show_error("error.create_subset", exc)

        def _replace_fonts(self) -> None:
            try:
                profile = self._profile()
                output = replace_font_slots(
                    profile.font.source_gfx,
                    profile.font.output_gfx,
                    {slot.character_id: slot.font_file for slot in profile.font.slots},
                    ffdec_cli=profile.font.ffdec or None,
                )
                self._write_log(self._t("log.wrote", path=output))
            except Exception as exc:
                self._show_error("error.replace_fonts", exc)

        def _build_font_pak(self) -> None:
            try:
                profile = self._profile()
                output_gfx = Path(profile.font.output_gfx).expanduser().resolve()
                output_pak = Path(profile.font.output_pak).expanduser().resolve()
                if not output_gfx.is_file():
                    raise FileNotFoundError(output_gfx)
                with tempfile.TemporaryDirectory(prefix="cryengine_font_overlay_") as temporary:
                    staged = Path(temporary) / "Libs" / "UI" / "exported_files" / "gfxfontlib.gfx"
                    staged.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(output_gfx, staged)
                    build_pak({"Libs/UI/exported_files/gfxfontlib.gfx": staged}, output_pak)
                self._write_log(self._t("log.wrote", path=output_pak))
            except Exception as exc:
                self._show_error("error.build_font_pak", exc)

        def _list_pak(self) -> None:
            try:
                profile = self._profile()
                archive = scan_pak(profile.source_pak)
                self._write_log("\n".join(f"{entry.size:>10}  {entry.path}" for entry in archive.entries))
            except Exception as exc:
                self._show_error("error.list_pak", exc)

        def _extract_pak(self) -> None:
            try:
                profile = self._profile()
                values = self._values()
                destination = values.get("pak_extract_dir", "").strip()
                if not destination:
                    raise ValueError("extract destination is required")
                match = values.get("pak_extract_match", "").strip() or None
                written = extract_pak(profile.source_pak, destination, match=match)
                self._write_log(self._t("log.extracted", count=len(written), path=Path(destination).expanduser().resolve()))
            except Exception as exc:
                self._show_error("error.extract_pak", exc)

        def _install_dry_run(self) -> None:
            try:
                planned = plan_profile_install(self._profile())
                self._write_log(json.dumps([self._installed_item_dict(item) for item in planned], ensure_ascii=False, indent=2))
            except Exception as exc:
                self._show_error("error.install_dry_run", exc)

        def _install(self, messagebox: Any) -> None:
            try:
                profile = self._profile()
                if not messagebox.askyesno(self._t("confirm.install.title"), self._t("confirm.install.body")):
                    self._write_log(self._t("log.install_cancelled"))
                    return
                record = install_profile(profile)
                self._write_log(
                    f"{self._t('log.installed', count=len(record.items))}\n"
                    f"{self._t('log.record', path=profile.install.record)}"
                )
            except Exception as exc:
                self._show_error("error.install", exc)

        def _rollback(self, messagebox: Any) -> None:
            try:
                profile = self._profile()
                if not messagebox.askyesno(self._t("confirm.rollback.title"), self._t("confirm.rollback.body")):
                    self._write_log(self._t("log.rollback_cancelled"))
                    return
                record = rollback_profile(profile)
                self._write_log(self._t("log.restored", count=len(record.items)))
            except Exception as exc:
                self._show_error("error.rollback", exc)

        @staticmethod
        def _installed_item_dict(item: InstalledItem) -> dict[str, Any]:
            return {
                "source": str(item.source),
                "destination": str(item.destination),
                "destination_existed": item.destination_existed,
                "backup_sha256": item.backup_sha256,
                "installed_sha256": item.installed_sha256,
            }

        def _write_log(self, text: str) -> None:
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")

        def _show_error(self, title: str, exc: Exception) -> None:
            self._write_log(self._t("log.error", message=str(exc)))
            messagebox.showerror(self._t(title), str(exc))

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise RuntimeError("no graphical display is available; use the cry-localize CLI") from exc
    App(root)
    root.mainloop()
