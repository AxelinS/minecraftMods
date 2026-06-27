"""
gui.py
------
Main application window built with CustomTkinter.

Layout (left-to-right / top-to-bottom):
  ┌──────────────────────────────────────────────────────┐
  │  Header: project path + folder selector              │
  ├──────────────────────────────────────────────────────┤
  │  Version panel  │  Scan stats panel                  │
  ├─────────────────┴──────────────────────────────────  │
  │  Action buttons row                                  │
  ├──────────────────────────────────────────────────────┤
  │  Log area (scrolled text)                            │
  └──────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
from typing import Optional

import customtkinter as ctk

from changelog import ChangelogEntry, ChangelogManager
from config import ConfigManager
from logger import LogLevel, LogRecord, get_logger
from manifest import ManifestDiff, ManifestDocument, ManifestManager
from scanner import ScanResult, Scanner
from utils import format_duration, format_size
from versioning import VersionError, VersionManager

log = get_logger()


# ---------------------------------------------------------------------------
# Colour aliases (kept minimal for easy theming)
# ---------------------------------------------------------------------------
COLOR_ADD = "#27ae60"
COLOR_MOD = "#f39c12"
COLOR_DEL = "#e74c3c"
COLOR_INFO = "#3b82d4"
COLOR_WARN = "#f39c12"
COLOR_ERR = "#e74c3c"
COLOR_MUTED = "#57606a"


class App(ctk.CTk):
    """Root application window.

    Parameters
    ----------
    config_manager:
        Application configuration manager (injected for testability).
    """

    def __init__(self, config_manager: ConfigManager) -> None:
        super().__init__()

        self._cfg = config_manager
        cfg = self._cfg.config

        # ── State ──────────────────────────────────────────────────────
        self._project_path: Optional[Path] = (
            Path(cfg.last_project_path) if cfg.last_project_path else None
        )
        self._scan_result: Optional[ScanResult] = None
        self._manifest_doc: Optional[ManifestDocument] = None
        self._diff: Optional[ManifestDiff] = None
        self._current_version: str = "—"
        self._new_version: str = "—"

        # ── Window setup ───────────────────────────────────────────────
        ctk.set_appearance_mode(cfg.theme)
        ctk.set_default_color_theme("blue")

        self.title("Modpack Manager")
        self.geometry(f"{cfg.window_width}x{cfg.window_height}")
        self.minsize(900, 600)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── Build UI ───────────────────────────────────────────────────
        self._build_ui()

        # ── Logger listener ────────────────────────────────────────────
        log.add_listener(self._on_log_record)

        # ── Load initial project if remembered ─────────────────────────
        if self._project_path and self._project_path.exists():
            self._refresh_version_display()

        log.info("Modpack Manager iniciado.")

    # ==================================================================
    # UI construction
    # ==================================================================

    def _build_ui(self) -> None:
        """Create and layout all widgets."""
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_version_and_stats()
        self._build_action_buttons()
        self._build_log_area()

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(header, text="Proyecto:", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, padx=(16, 8), pady=12, sticky="w"
        )

        self._project_var = tk.StringVar(
            value=str(self._project_path) if self._project_path else "Ninguna carpeta seleccionada"
        )
        ctk.CTkEntry(
            header,
            textvariable=self._project_var,
            state="readonly",
            font=ctk.CTkFont(size=13),
        ).grid(row=0, column=1, padx=8, pady=12, sticky="ew")

        ctk.CTkButton(
            header,
            text="📂  Seleccionar carpeta",
            command=self._select_project,
            width=180,
        ).grid(row=0, column=2, padx=8, pady=12)

        ctk.CTkButton(
            header,
            text="🗂  Abrir carpeta",
            command=self._open_project_folder,
            width=140,
            fg_color="transparent",
            border_width=1,
        ).grid(row=0, column=3, padx=(0, 16), pady=12)

    # ------------------------------------------------------------------
    # Version + stats
    # ------------------------------------------------------------------

    def _build_version_and_stats(self) -> None:
        middle = ctk.CTkFrame(self)
        middle.grid(row=1, column=0, sticky="ew", padx=16, pady=(8, 4))
        middle.grid_columnconfigure(0, weight=1)
        middle.grid_columnconfigure(1, weight=1)

        self._build_version_panel(middle)
        self._build_stats_panel(middle)

    def _build_version_panel(self, parent: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(parent)
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)

        ctk.CTkLabel(frame, text="Versión", font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, columnspan=4, padx=16, pady=(12, 4), sticky="w"
        )

        ctk.CTkLabel(frame, text="Actual:", anchor="e").grid(
            row=1, column=0, padx=(16, 4), pady=4, sticky="e"
        )
        self._lbl_current_ver = ctk.CTkLabel(
            frame, text=self._current_version, font=ctk.CTkFont(size=13, weight="bold")
        )
        self._lbl_current_ver.grid(row=1, column=1, padx=(0, 16), pady=4, sticky="w")

        ctk.CTkLabel(frame, text="Nueva:", anchor="e").grid(
            row=2, column=0, padx=(16, 4), pady=4, sticky="e"
        )
        self._lbl_new_ver = ctk.CTkLabel(
            frame, text=self._new_version, font=ctk.CTkFont(size=13, weight="bold")
        )
        self._lbl_new_ver.grid(row=2, column=1, padx=(0, 16), pady=4, sticky="w")

        # Increment buttons
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.grid(row=3, column=0, columnspan=4, padx=12, pady=(4, 8), sticky="ew")

        for label, inc_type in [("Patch", "patch"), ("Minor", "minor"), ("Major", "major")]:
            ctk.CTkButton(
                btn_frame,
                text=f"↑ {label}",
                width=90,
                command=lambda t=inc_type: self._increment_version(t),
            ).pack(side="left", padx=4, pady=4)

        # Manual version entry
        manual_frame = ctk.CTkFrame(frame, fg_color="transparent")
        manual_frame.grid(row=4, column=0, columnspan=4, padx=12, pady=(0, 12), sticky="ew")

        ctk.CTkLabel(manual_frame, text="Manual:").pack(side="left", padx=(0, 6))
        self._manual_version_var = tk.StringVar()
        self._manual_entry = ctk.CTkEntry(
            manual_frame,
            textvariable=self._manual_version_var,
            placeholder_text="1.0.0",
            width=90,
        )
        self._manual_entry.pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            manual_frame,
            text="Aplicar",
            width=70,
            command=self._apply_manual_version,
        ).pack(side="left")

    def _build_stats_panel(self, parent: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(parent)
        frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=0)

        ctk.CTkLabel(frame, text="Estadísticas del escaneo", font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, columnspan=2, padx=16, pady=(12, 4), sticky="w"
        )

        stats = [
            ("Total archivos:", "_stat_total_files"),
            ("Tamaño total:", "_stat_total_size"),
            ("Archivos nuevos:", "_stat_added"),
            ("Archivos modificados:", "_stat_modified"),
            ("Archivos eliminados:", "_stat_deleted"),
            ("Tiempo de escaneo:", "_stat_elapsed"),
        ]

        for i, (label_text, attr) in enumerate(stats, start=1):
            ctk.CTkLabel(frame, text=label_text, anchor="e").grid(
                row=i, column=0, padx=(16, 4), pady=2, sticky="e"
            )
            lbl = ctk.CTkLabel(frame, text="—", anchor="w")
            lbl.grid(row=i, column=1, padx=(0, 16), pady=2, sticky="w")
            setattr(self, attr, lbl)

    # ------------------------------------------------------------------
    # Action buttons
    # ------------------------------------------------------------------

    def _build_action_buttons(self) -> None:
        frame = ctk.CTkFrame(self)
        frame.grid(row=2, column=0, sticky="ew", padx=16, pady=4)

        buttons = [
            ("🔍  Escanear proyecto", self._run_scan, None),
            ("📄  Generar Manifest", self._generate_manifest, None),
            ("📝  Generar Changelog", self._generate_changelog, None),
            ("💾  Exportar todo", self._export_all, "transparent"),
        ]

        for text, cmd, fg in buttons:
            kw = {"fg_color": fg, "border_width": 1} if fg else {}
            ctk.CTkButton(frame, text=text, command=cmd, width=180, **kw).pack(
                side="left", padx=8, pady=10
            )

    # ------------------------------------------------------------------
    # Log area
    # ------------------------------------------------------------------

    def _build_log_area(self) -> None:
        frame = ctk.CTkFrame(self)
        frame.grid(row=3, column=0, sticky="nsew", padx=16, pady=(4, 16))
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(hdr, text="Log", font=ctk.CTkFont(size=13, weight="bold")).pack(
            side="left", padx=12, pady=(8, 4)
        )
        ctk.CTkButton(
            hdr,
            text="Limpiar",
            width=70,
            height=24,
            fg_color="transparent",
            border_width=1,
            command=self._clear_log,
        ).pack(side="right", padx=12, pady=(8, 4))

        self._log_box = ctk.CTkTextbox(frame, wrap="word", font=ctk.CTkFont(family="Consolas", size=12))
        self._log_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._log_box.configure(state="disabled")

        # Colour tags for different log levels
        self._log_box._textbox.tag_config("INFO", foreground=COLOR_INFO)
        self._log_box._textbox.tag_config("WARNING", foreground=COLOR_WARN)
        self._log_box._textbox.tag_config("ERROR", foreground=COLOR_ERR)
        self._log_box._textbox.tag_config("DEBUG", foreground=COLOR_MUTED)

    # ==================================================================
    # Handlers — project management
    # ==================================================================

    def _select_project(self) -> None:
        path_str = filedialog.askdirectory(title="Seleccionar carpeta del proyecto")
        if not path_str:
            return
        self._project_path = Path(path_str)
        self._project_var.set(path_str)
        self._cfg.config.last_project_path = path_str
        self._cfg.save()
        self._refresh_version_display()
        log.info(f"Proyecto seleccionado: {path_str}")

    def _open_project_folder(self) -> None:
        if not self._project_path:
            messagebox.showwarning("Sin proyecto", "Selecciona primero una carpeta de proyecto.")
            return
        if os.name == "nt":
            os.startfile(str(self._project_path))  # type: ignore[attr-defined]
        else:
            import subprocess
            subprocess.Popen(["xdg-open", str(self._project_path)])

    # ==================================================================
    # Handlers — versioning
    # ==================================================================

    def _refresh_version_display(self) -> None:
        if not self._project_path:
            return
        try:
            vm = VersionManager(self._project_path)
            self._current_version = vm.read()
            self._new_version = self._current_version
            self._lbl_current_ver.configure(text=self._current_version)
            self._lbl_new_ver.configure(text=self._new_version)
        except VersionError:
            # version.json doesn't exist yet; that's fine
            self._current_version = "—"
            self._new_version = "—"
            self._lbl_current_ver.configure(text="—")
            self._lbl_new_ver.configure(text="—")

    def _increment_version(self, increment_type: str) -> None:
        if not self._project_path:
            messagebox.showwarning("Sin proyecto", "Selecciona una carpeta de proyecto primero.")
            return
        try:
            vm = VersionManager(self._project_path)
            old, new = vm.increment(increment_type)
            self._current_version = new
            self._new_version = new
            self._lbl_current_ver.configure(text=new)
            self._lbl_new_ver.configure(text=new)
            self._cfg.config.last_increment_type = increment_type
            self._cfg.save()
        except (VersionError, ValueError) as exc:
            messagebox.showerror("Error de versión", str(exc))

    def _apply_manual_version(self) -> None:
        version = self._manual_version_var.get().strip()
        if not version:
            return
        if not self._project_path:
            messagebox.showwarning("Sin proyecto", "Selecciona una carpeta de proyecto primero.")
            return
        try:
            vm = VersionManager(self._project_path)
            vm.write(version)
            self._current_version = version
            self._new_version = version
            self._lbl_current_ver.configure(text=version)
            self._lbl_new_ver.configure(text=version)
            self._manual_version_var.set("")
        except VersionError as exc:
            messagebox.showerror("Versión inválida", str(exc))

    # ==================================================================
    # Handlers — scanning
    # ==================================================================

    def _run_scan(self) -> None:
        if not self._project_path:
            messagebox.showwarning("Sin proyecto", "Selecciona una carpeta de proyecto primero.")
            return
        log.info("Iniciando escaneo…")
        # Run in background thread to keep GUI responsive
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self) -> None:
        try:
            scanner = Scanner(self._project_path)  # type: ignore[arg-type]
            scanner.validate()
            result = scanner.scan()
            self._scan_result = result

            # Compute diff against previous manifest
            mm = ManifestManager(self._project_path)  # type: ignore[arg-type]
            previous = mm.load_previous()
            version = self._current_version if self._current_version != "—" else "0.0.0"
            doc = mm.build(version, result)
            diff = mm.diff(previous, doc)
            self._manifest_doc = doc
            self._diff = diff

            # Update stats on main thread
            self.after(0, lambda: self._update_stats(result, diff))
        except ValueError as exc:
            self.after(0, lambda: messagebox.showerror("Error de escaneo", str(exc)))
        except Exception as exc:  # noqa: BLE001
            log.error(f"Error inesperado durante el escaneo: {exc}")

    def _update_stats(self, result: ScanResult, diff: ManifestDiff) -> None:
        self._stat_total_files.configure(text=str(result.total_files))
        self._stat_total_size.configure(text=format_size(result.total_size))
        self._stat_added.configure(text=str(len(diff.added)))
        self._stat_modified.configure(text=str(len(diff.modified)))
        self._stat_deleted.configure(text=str(len(diff.deleted)))
        self._stat_elapsed.configure(text=format_duration(result.elapsed_seconds))

        # Print diff summary to log
        log.info(f"Nueva versión (pendiente de guardar): {self._current_version}")
        for line in diff.summary_lines():
            log.info(line)

    # ==================================================================
    # Handlers — manifest
    # ==================================================================

    def _generate_manifest(self) -> None:
        if self._manifest_doc is None or self._diff is None:
            messagebox.showinfo(
                "Sin datos",
                "Primero ejecuta un escaneo (🔍 Escanear proyecto).",
            )
            return
        if not self._project_path:
            return
        try:
            mm = ManifestManager(self._project_path)
            mm.save(self._manifest_doc)
            messagebox.showinfo(
                "Manifest generado",
                f"manifest.json guardado correctamente.\n\nVersiones: {self._manifest_doc.version}\nArchivos: {len(self._manifest_doc.files)}",
            )
        except OSError as exc:
            messagebox.showerror("Error al guardar", str(exc))

    # ==================================================================
    # Handlers — changelog
    # ==================================================================

    def _generate_changelog(self) -> None:
        if self._diff is None:
            messagebox.showinfo(
                "Sin datos",
                "Primero ejecuta un escaneo (🔍 Escanear proyecto).",
            )
            return
        if not self._project_path:
            return

        # Ask for optional manual notes
        notes = simpledialog.askstring(
            "Notas del changelog",
            "Agrega notas manuales para esta versión (opcional):",
            parent=self,
        ) or ""

        try:
            version = self._current_version if self._current_version != "—" else "0.0.0"
            cm = ChangelogManager(self._project_path)
            entry = ChangelogEntry(version=version, diff=self._diff, notes=notes)
            cm.append_entry(entry)
            messagebox.showinfo(
                "Changelog generado",
                f"CHANGELOG.md actualizado para la versión {version}.",
            )
        except OSError as exc:
            messagebox.showerror("Error al guardar", str(exc))

    # ==================================================================
    # Handlers — export
    # ==================================================================

    def _export_all(self) -> None:
        if self._manifest_doc is None or self._diff is None:
            messagebox.showinfo(
                "Sin datos",
                "Primero ejecuta un escaneo (🔍 Escanear proyecto).",
            )
            return

        dest_str = filedialog.askdirectory(title="Seleccionar carpeta de exportación")
        if not dest_str:
            return
        dest = Path(dest_str)

        try:
            version = self._manifest_doc.version

            mm = ManifestManager(self._project_path)  # type: ignore[arg-type]
            mm.export(dest / "manifest.json", self._manifest_doc)

            cm = ChangelogManager(self._project_path)  # type: ignore[arg-type]
            cm.export(dest / "CHANGELOG.md")
            cm.export_summary_txt(dest / f"summary_{version}.txt", version, self._diff)

            messagebox.showinfo(
                "Exportación completa",
                f"Archivos exportados a:\n{dest_str}",
            )
        except OSError as exc:
            messagebox.showerror("Error de exportación", str(exc))

    # ==================================================================
    # Log area
    # ==================================================================

    def _on_log_record(self, record: LogRecord) -> None:
        """Called from any thread; schedules a GUI update on the main thread."""
        self.after(0, lambda: self._append_log(record))

    def _append_log(self, record: LogRecord) -> None:
        self._log_box.configure(state="normal")
        self._log_box._textbox.insert("end", str(record) + "\n", record.level.value)
        self._log_box._textbox.see("end")
        self._log_box.configure(state="disabled")

    def _clear_log(self) -> None:
        self._log_box.configure(state="normal")
        self._log_box.delete("0.0", "end")
        self._log_box.configure(state="disabled")

    # ==================================================================
    # Window lifecycle
    # ==================================================================

    def _on_close(self) -> None:
        """Save window geometry before closing."""
        self._cfg.config.window_width = self.winfo_width()
        self._cfg.config.window_height = self.winfo_height()
        self._cfg.save()
        log.remove_listener(self._on_log_record)
        self.destroy()
