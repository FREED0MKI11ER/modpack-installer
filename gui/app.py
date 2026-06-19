"""Modern GUI for the modpack installer (customtkinter).

Single-window flow:
  - Header: icon + title + installer version
  - Pack info line + Manifest URL row
  - Scrollable list of launchers (checkbox + detected badge + path + Browse)
  - Install/Update button, progress bar, status line, log

Appearance follows the system light/dark setting. Neutral (no brand accent).
Install runs on a worker thread; UI updates are marshalled back via a queue.
"""

import os
import queue
import sys
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core.config import load_config
from core.engine import Engine
from core import java_check

# Neutral palette. Status badges keep informational colors; no brand accent.
DETECTED_COLOR = ("#1b7f3b", "#4ade80")   # (light, dark)
NOTFOUND_COLOR = ("#b26a00", "#fbbf24")
MUTED_COLOR = ("#555555", "#a0a0a0")


def _asset_dirs():
    dirs = []
    if getattr(sys, "frozen", False):
        dirs.append(os.path.dirname(sys.executable))
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            dirs.append(meipass)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dirs.append(root)
    dirs.append(os.path.join(root, "build"))
    return dirs


def _find_asset(name):
    for d in _asset_dirs():
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None


class LauncherRow:
    def __init__(self, parent, target, on_toggle=None):
        self.target = target
        self.on_toggle = on_toggle or (lambda: None)
        self.var = ctk.BooleanVar(value=False)

        self.frame = ctk.CTkFrame(parent, corner_radius=8)
        self.frame.pack(fill="x", padx=6, pady=4)
        self.frame.grid_columnconfigure(2, weight=1)

        self.check = ctk.CTkCheckBox(
            self.frame, text=target.name, variable=self.var, width=200,
            command=lambda: self.on_toggle())
        self.check.grid(row=0, column=0, sticky="w", padx=(12, 8), pady=10)

        # status pill (pack state for detected; "not found" for undetected)
        self.status = "not_installed" if target.present else None
        self.status_lbl = ctk.CTkLabel(
            self.frame, text="", width=160,
            font=ctk.CTkFont(size=12, weight="bold"))
        self.status_lbl.grid(row=0, column=1, sticky="w", padx=4)
        self._render_status()

        self.path_var = ctk.StringVar(
            value=target.detected_path or "(not detected - click Browse)")
        self.path_entry = ctk.CTkEntry(self.frame, textvariable=self.path_var)
        self.path_entry.grid(row=0, column=2, sticky="we", padx=8)

        self.browse_btn = ctk.CTkButton(
            self.frame, text="Browse", width=80, command=self._browse,
            fg_color="transparent", border_width=1,
            text_color=("gray20", "gray90"), border_color=("gray60", "gray45"),
            hover_color=("gray85", "gray25"))
        self.browse_btn.grid(row=0, column=3, sticky="e", padx=(4, 12))

    def _render_status(self):
        if not self.target.present:
            self.status_lbl.configure(text="○ not found",
                                      text_color=NOTFOUND_COLOR)
            return
        label, color = {
            "up_to_date": ("Pack up to date", DETECTED_COLOR),
            "out_of_date": ("Pack out of date", NOTFOUND_COLOR),
            "not_installed": ("Detected, pack not installed", MUTED_COLOR),
        }.get(self.status, ("Detected, pack not installed", MUTED_COLOR))
        self.status_lbl.configure(text=label, text_color=color)

    def set_status(self, status):
        self.status = status
        self._render_status()

    def _browse(self):
        chosen = filedialog.askdirectory(
            title=f"Select install folder for {self.target.name}")
        if chosen:
            self.path_var.set(chosen)
            self.var.set(True)
            self.on_toggle()

    def destroy(self):
        self.frame.destroy()

    @property
    def selected(self):
        return self.var.get()

    @property
    def root_path(self):
        p = self.path_var.get().strip()
        return p if p and not p.startswith("(") else None


class InstallerApp:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.engine = None
        self.rows = []
        self.msg_queue = queue.Queue()
        self._busy = False

        self.app_version = self.cfg.get("version", "dev")
        self.base_title = self.cfg.get("title", "Modpack Installer")
        root.title(f"{self.base_title}  {self.app_version}")
        root.geometry("900x680")
        root.minsize(780, 600)
        self._set_window_icon()

        self._build_header()
        self._build_launcher_area()
        self._build_footer()

        self._poll_queue()
        self.root.after(200, self.load_manifest)

    # ---------- helpers ----------
    @staticmethod
    def _fmt_date(iso):
        import datetime
        try:
            d = datetime.date.fromisoformat(iso)
            return f"{d.month}/{d.day}/{d.year}"
        except (ValueError, TypeError):
            return iso

    def _set_window_icon(self):
        # Keep the .ico as the taskbar/window icon; no in-window header image.
        ico = _find_asset("icon.ico")
        if ico:
            try:
                self.root.iconbitmap(ico)
            except Exception:  # noqa: BLE001
                pass

    # ---------- UI construction ----------
    def _build_header(self):
        # Plain header: title + version text on the normal background.
        head = ctk.CTkFrame(self.root, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(16, 0))
        self.title_lbl = ctk.CTkLabel(
            head, text=self.base_title,
            font=ctk.CTkFont(size=20, weight="bold"))
        self.title_lbl.pack(anchor="w")
        self.version_lbl = ctk.CTkLabel(
            head, text=f"Installer {self.app_version}",
            text_color=MUTED_COLOR, font=ctk.CTkFont(size=12))
        self.version_lbl.pack(anchor="w")

        # Pack info + manifest URL.
        top = ctk.CTkFrame(self.root, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(12, 4))
        self.info_lbl = ctk.CTkLabel(
            top, text="Loading pack info...", justify="left",
            text_color=MUTED_COLOR, font=ctk.CTkFont(size=13))
        self.info_lbl.pack(anchor="w", pady=(0, 8))

        url_row = ctk.CTkFrame(top, fg_color="transparent")
        url_row.pack(fill="x")
        ctk.CTkLabel(url_row, text="Manifest URL:").pack(side="left")
        self.url_var = ctk.StringVar(value=self.cfg.get("manifestUrl", ""))
        self.url_entry = ctk.CTkEntry(url_row, textvariable=self.url_var)
        self.url_entry.pack(side="left", fill="x", expand=True, padx=8)
        ctk.CTkButton(
            url_row, text="Reload", width=80,
            command=self.load_manifest).pack(side="left")

    def _build_launcher_area(self):
        section = ctk.CTkFrame(self.root, fg_color="transparent")
        section.pack(fill="both", expand=False, padx=20, pady=(8, 4))

        ctk.CTkLabel(
            section, text="Select launcher(s) to install / update",
            font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w")

        self.hint_lbl = ctk.CTkLabel(
            section,
            text=("Tip: if your launcher isn't detected, tick it and click "
                  "Browse to select its folder (the one containing 'instances' "
                  "or '.minecraft')."),
            text_color=MUTED_COLOR, justify="left", wraplength=820,
            font=ctk.CTkFont(size=12))
        self.hint_lbl.pack(anchor="w", pady=(2, 6))

        self.rows_frame = ctk.CTkScrollableFrame(section, height=200)
        self.rows_frame.pack(fill="both", expand=True)

    def _build_footer(self):
        bot = ctk.CTkFrame(self.root, fg_color="transparent")
        bot.pack(fill="both", expand=True, padx=20, pady=(4, 16))

        ctrl = ctk.CTkFrame(bot, fg_color="transparent")
        ctrl.pack(fill="x")
        self.install_btn = ctk.CTkButton(
            ctrl, text="Install / Update", command=self.start_install,
            state="disabled", width=160, height=40,
            font=ctk.CTkFont(size=14, weight="bold"))
        self.install_btn.pack(side="left")

        self.progress = ctk.CTkProgressBar(ctrl, mode="determinate")
        self.progress.set(0)
        self.progress.pack(side="left", fill="x", expand=True, padx=14)

        self.status_var = ctk.StringVar(value="Starting...")
        self.status_lbl = ctk.CTkLabel(
            bot, textvariable=self.status_var, text_color=MUTED_COLOR,
            anchor="w", font=ctk.CTkFont(size=12))
        self.status_lbl.pack(fill="x", pady=(8, 0))

        self.log = ctk.CTkTextbox(bot, height=180, font=ctk.CTkFont(
            family="Consolas", size=12))
        self.log.configure(state="disabled")
        self.log.pack(fill="both", expand=True, pady=(8, 0))

    # ---------- thread-safe queue plumbing ----------
    def _log(self, msg):
        self.msg_queue.put(("log", msg))

    def _status(self, text):
        self.msg_queue.put(("status", text))

    def _busy_start(self):
        self.msg_queue.put(("busy", True))

    def _busy_stop(self):
        self.msg_queue.put(("busy", False))

    def _set_progress(self, current, total, name=None):
        self.msg_queue.put(("progress", (current, total)))
        if name:
            self.msg_queue.put(
                ("status", f"Downloading {name} ({current}/{total})"))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self.log.configure(state="normal")
                    self.log.insert("end", payload + "\n")
                    self.log.see("end")
                    self.log.configure(state="disabled")
                elif kind == "status":
                    self.status_var.set(payload)
                elif kind == "busy":
                    self._set_busy(payload)
                elif kind == "progress":
                    cur, total = payload
                    self._set_busy(False)
                    self.progress.set(cur / max(total, 1))
                elif kind == "done":
                    self._on_install_done(payload)
                elif kind == "loaded":
                    self._on_manifest_loaded()
                elif kind == "java":
                    self._on_java_result(payload)
                elif kind == "statuses":
                    self._on_statuses(payload)
                elif kind == "load_error":
                    self._set_busy(False)
                    self.status_var.set("Failed to load pack.")
                    self.info_lbl.configure(
                        text=f"Failed to load pack: {payload}",
                        text_color=("#c62828", "#ff6b6b"))
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _set_busy(self, on):
        if on and not self._busy:
            self.progress.configure(mode="indeterminate")
            self.progress.start()
            self._busy = True
        elif not on and self._busy:
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.progress.set(0)
            self._busy = False

    # ---------- manifest loading ----------
    def load_manifest(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Manifest URL", "Please enter a manifest URL.")
            return
        self.info_lbl.configure(text="Loading pack info...",
                                text_color=MUTED_COLOR)
        self.install_btn.configure(state="disabled")
        self._busy_start()
        self._status("Connecting to server...")
        threading.Thread(target=self._load_worker, args=(url,),
                         daemon=True).start()

    def _load_worker(self, url):
        try:
            eng = Engine(url)
            eng.load(log=self._log, status=self._status)
            self.engine = eng
            self.msg_queue.put(("loaded", None))
            jv = java_check.java_version()
            self.msg_queue.put(("java", jv))
            # Pack status per detected launcher (marker read; fast).
            try:
                self.msg_queue.put(("statuses", eng.statuses()))
            except Exception:  # noqa: BLE001 - non-fatal
                pass
        except Exception as e:  # noqa: BLE001
            self.msg_queue.put(("load_error", str(e)))

    def _info_text(self, java_line):
        m = self.engine.manifest
        return (f"{m.pack_name}   •   MC {m.minecraft}   •   Fabric "
                f"{self.engine.loader_version}   •   pack updated "
                f"{self._fmt_date(m.version)}\n{java_line}")

    def _on_manifest_loaded(self):
        self._set_busy(False)
        self.status_var.set("Ready. Choose launcher(s) and click Install / Update.")
        m = self.engine.manifest
        self.info_lbl.configure(text=self._info_text("Java: checking..."),
                                text_color=MUTED_COLOR)
        self.title_lbl.configure(text=m.pack_name)

        for r in self.rows:
            r.destroy()
        self.rows = []
        targets = self.engine.detect_targets()
        ordered = [t for t in targets if t.present] + \
                  [t for t in targets if not t.present]
        for target in ordered:
            self.rows.append(
                LauncherRow(self.rows_frame, target,
                            on_toggle=self._update_button_label))
        self.install_btn.configure(state="normal")
        self._update_button_label()
        self._log("Ready. Choose launcher(s) and click Install / Update.")

    def _on_java_result(self, jv):
        if self.engine is None or self.engine.manifest is None:
            return
        jv = jv or "not found (your launcher likely bundles Java)"
        self.info_lbl.configure(text=self._info_text(f"Java: {jv}"),
                                text_color=MUTED_COLOR)

    def _on_statuses(self, statuses):
        for r in self.rows:
            if r.target.name in statuses:
                r.set_status(statuses[r.target.name])
        self._update_button_label()

    def _update_button_label(self):
        """Switch the button between Install / Update / Install / Update based
        on the selected rows' install state."""
        chosen = [r for r in self.rows if r.selected]
        if not chosen:
            self.install_btn.configure(text="Install / Update")
            return
        states = set()
        for r in chosen:
            if r.target.present and r.status in ("up_to_date", "out_of_date"):
                states.add("installed")
            else:
                states.add("new")
        if states == {"installed"}:
            self.install_btn.configure(text="Update")
        elif states == {"new"}:
            self.install_btn.configure(text="Install")
        else:
            self.install_btn.configure(text="Install / Update")

    # ---------- install ----------
    def start_install(self):
        chosen = [r for r in self.rows if r.selected]
        if not chosen:
            messagebox.showwarning("No selection",
                                   "Tick at least one launcher to install on.")
            return
        for r in chosen:
            if not r.root_path:
                messagebox.showwarning(
                    "Missing path",
                    f"{r.target.name} has no install folder. Click Browse to set it.")
                return
        self.install_btn.configure(state="disabled")
        self.progress.set(0)
        self._busy_start()
        self._status("Preparing install...")
        threading.Thread(target=self._install_worker, args=(chosen,),
                         daemon=True).start()

    def _install_worker(self, rows):
        results = []
        errors = []
        for r in rows:
            try:
                self._status(f"Setting up {r.target.name}...")
                self._busy_start()
                res = self.engine.install(
                    r.target, root_override=r.root_path,
                    log=self._log, progress=self._set_progress)
                results.append(res)
            except Exception as e:  # noqa: BLE001
                errors.append((r.target.name, str(e)))
                self._log(f"ERROR on {r.target.name}: {e}")
        self.msg_queue.put(("done", (results, errors)))

    def _on_install_done(self, payload):
        results, errors = payload
        self._set_busy(False)
        self.progress.set(1 if results and not errors else 0)
        self.status_var.set("Done." if not errors else "Finished with errors.")
        self.install_btn.configure(state="normal")
        lines = []
        for res in results:
            lines.append(f"[OK] {res.launcher}: {res.instance_name}\n    {res.notes}")
        for name, err in errors:
            lines.append(f"[FAILED] {name}: {err}")
        summary = "\n\n".join(lines) if lines else "Nothing was installed."
        if errors:
            messagebox.showwarning("Finished with errors", summary)
        else:
            messagebox.showinfo("Done", summary)


def main():
    ctk.set_appearance_mode("System")   # follow OS light/dark
    ctk.set_default_color_theme("blue")  # ctk default neutral theme
    root = ctk.CTk()
    InstallerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
