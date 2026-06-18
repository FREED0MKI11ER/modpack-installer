"""Tkinter GUI for the modpack installer.

Single-window flow:
  - Top: pack title + manifest URL field (editable; defaults from config.json)
  - Middle: scrollable list of launchers, each a checkbox + detected-path label
            + Browse button to override the install root
  - Bottom: Install/Update button, progress bar, scrolling log
Install runs on a worker thread; UI updates are marshalled back via .after().
"""

import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from core.config import load_config
from core.engine import Engine
from core import java_check


class LauncherRow:
    def __init__(self, parent, target):
        self.target = target
        self.var = tk.BooleanVar(value=False)
        self.path_var = tk.StringVar(
            value=target.detected_path or "(not detected - click Browse)")

        self.frame = ttk.Frame(parent)
        self.frame.pack(fill="x", padx=4, pady=3)

        self.check = ttk.Checkbutton(
            self.frame, text=target.name, variable=self.var, width=26)
        self.check.grid(row=0, column=0, sticky="w")

        status = "● detected" if target.present else "○ not found"
        self.status_lbl = ttk.Label(
            self.frame, text=status, width=12,
            style="Detected.TLabel" if target.present else "NotFound.TLabel")
        self.status_lbl.grid(row=0, column=1, sticky="w")

        self.path_entry = ttk.Entry(self.frame, textvariable=self.path_var,
                                    width=48)
        self.path_entry.grid(row=0, column=2, sticky="we", padx=4)

        self.browse_btn = ttk.Button(self.frame, text="Browse...",
                                     command=self._browse, width=10)
        self.browse_btn.grid(row=0, column=3, sticky="e")

        self.frame.columnconfigure(2, weight=1)

    def _browse(self):
        chosen = filedialog.askdirectory(title=f"Select install folder for {self.target.name}")
        if chosen:
            self.path_var.set(chosen)
            self.var.set(True)

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

        self.app_version = self.cfg.get("version", "dev")
        base_title = self.cfg.get("title", "Modpack Installer")
        root.title(f"{base_title}  {self.app_version}")
        root.geometry("840x640")
        root.minsize(740, 560)
        self._set_window_icon()
        self._init_style()

        self._build_header()
        self._build_launcher_area()
        self._build_footer()

        self._poll_queue()
        # Auto-load the manifest on startup
        self.root.after(200, self.load_manifest)

    # ---------- styling ----------
    # Purple palette matching the FS icon.
    ACCENT = "#582a9c"
    ACCENT_HOVER = "#6d3bbf"
    HEADER_BG = "#3d1e6e"
    HEADER_FG = "#f0ebff"
    BODY_BG = "#f5f3fa"

    def _init_style(self):
        style = ttk.Style()
        # Prefer a theme we can color; fall back gracefully on macOS aqua.
        for theme in ("clam", "vista", "default"):
            if theme in style.theme_names():
                try:
                    style.theme_use(theme)
                    break
                except tk.TclError:
                    continue

        base_font = ("Segoe UI", 10)
        try:
            self.root.configure(bg=self.BODY_BG)
        except tk.TclError:
            pass

        style.configure("TFrame", background=self.BODY_BG)
        style.configure("TLabel", background=self.BODY_BG, font=base_font)
        style.configure("TCheckbutton", background=self.BODY_BG, font=base_font)
        style.configure("TLabelframe", background=self.BODY_BG)
        style.configure("TLabelframe.Label", background=self.BODY_BG,
                        font=("Segoe UI", 10, "bold"))

        # Header styles.
        style.configure("Header.TFrame", background=self.HEADER_BG)
        style.configure("HeaderTitle.TLabel", background=self.HEADER_BG,
                        foreground=self.HEADER_FG, font=("Segoe UI", 16, "bold"))
        style.configure("HeaderSub.TLabel", background=self.HEADER_BG,
                        foreground="#c9b8ec", font=("Segoe UI", 9))

        # Info / status.
        style.configure("Info.TLabel", background=self.BODY_BG,
                        foreground="#333", font=("Segoe UI", 10))
        style.configure("Hint.TLabel", background=self.BODY_BG,
                        foreground="#666", font=("Segoe UI", 9))
        style.configure("Status.TLabel", background=self.BODY_BG,
                        foreground="#444", font=("Segoe UI", 9))

        # Accent primary button.
        style.configure("Accent.TButton", font=("Segoe UI", 11, "bold"),
                        foreground="white", background=self.ACCENT,
                        padding=(16, 8), borderwidth=0)
        style.map("Accent.TButton",
                  background=[("active", self.ACCENT_HOVER),
                              ("disabled", "#b9a9d6")],
                  foreground=[("disabled", "#eee")])

        # Accent progress bar.
        try:
            style.configure("Accent.Horizontal.TProgressbar",
                            background=self.ACCENT, troughcolor="#e2dcef",
                            borderwidth=0, thickness=14)
        except tk.TclError:
            pass

        # Status badges (detected / not found).
        style.configure("Detected.TLabel", background=self.BODY_BG,
                        foreground="#2e7d32", font=("Segoe UI", 9, "bold"))
        style.configure("NotFound.TLabel", background=self.BODY_BG,
                        foreground="#b26a00", font=("Segoe UI", 9, "bold"))

    @staticmethod
    def _fmt_date(iso):
        """Format an ISO date (YYYY-MM-DD) as M/D/YYYY; pass through otherwise."""
        import datetime
        try:
            d = datetime.date.fromisoformat(iso)
            return f"{d.month}/{d.day}/{d.year}"
        except (ValueError, TypeError):
            return iso

    # ---------- UI construction ----------
    def _set_window_icon(self):
        """Set the titlebar/taskbar icon and load the PNG for the header."""
        import os
        import sys
        self._icon_img = None
        dirs = []
        if getattr(sys, "frozen", False):
            dirs.append(os.path.dirname(sys.executable))
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                dirs.append(meipass)
        # project root (parent of gui/) and build/
        dirs.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        dirs.append(os.path.join(dirs[-1], "build"))

        # Always try to load the PNG (used by the header image and as a
        # cross-platform window icon fallback).
        for d in dirs:
            png = os.path.join(d, "icon.png")
            if os.path.isfile(png):
                try:
                    self._icon_img = tk.PhotoImage(file=png)
                    break
                except tk.TclError:
                    pass

        # Prefer .ico for the window/taskbar icon on Windows.
        for d in dirs:
            ico = os.path.join(d, "icon.ico")
            if os.path.isfile(ico):
                try:
                    self.root.iconbitmap(ico)
                    return
                except tk.TclError:
                    pass
        # Fallback: use the PNG as the window icon.
        if self._icon_img is not None:
            try:
                self.root.iconphoto(True, self._icon_img)
            except tk.TclError:
                pass

    def _build_header(self):
        # Colored header band with icon + title + version.
        band = ttk.Frame(self.root, style="Header.TFrame")
        band.pack(fill="x")
        inner = ttk.Frame(band, style="Header.TFrame")
        inner.pack(fill="x", padx=16, pady=12)

        if getattr(self, "_icon_img", None) is not None:
            try:
                small = self._icon_img.subsample(
                    max(1, self._icon_img.width() // 48))
                icon_lbl = tk.Label(inner, image=small, bg=self.HEADER_BG,
                                    borderwidth=0)
                icon_lbl.image = small
                icon_lbl.pack(side="left", padx=(0, 12))
            except tk.TclError:
                pass

        text_col = ttk.Frame(inner, style="Header.TFrame")
        text_col.pack(side="left", fill="x", expand=True)
        base_title = self.cfg.get("title", "Modpack Installer")
        self.title_lbl = ttk.Label(text_col, text=base_title,
                                   style="HeaderTitle.TLabel")
        self.title_lbl.pack(anchor="w")
        self.version_lbl = ttk.Label(
            text_col, text=f"Installer {self.app_version}",
            style="HeaderSub.TLabel")
        self.version_lbl.pack(anchor="w")

        # Pack info line below the band.
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=16, pady=(10, 4))
        self.info_lbl = ttk.Label(top, text="Loading pack info...",
                                  style="Info.TLabel")
        self.info_lbl.pack(anchor="w", pady=(0, 6))

        url_row = ttk.Frame(top)
        url_row.pack(fill="x")
        ttk.Label(url_row, text="Manifest URL:", style="TLabel").pack(side="left")
        self.url_var = tk.StringVar(value=self.cfg.get("manifestUrl", ""))
        self.url_entry = ttk.Entry(url_row, textvariable=self.url_var)
        self.url_entry.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(url_row, text="Reload", command=self.load_manifest).pack(side="left")

    def _build_launcher_area(self):
        mid = ttk.LabelFrame(self.root, text="Select launcher(s) to install / update")
        mid.pack(fill="both", expand=False, padx=12, pady=6)

        self.hint_lbl = ttk.Label(
            mid,
            text=("Tip: if your launcher isn't detected, tick it and click "
                  "Browse to select its folder (the one containing 'instances' "
                  "or '.minecraft')."),
            style="Hint.TLabel", wraplength=780, justify="left")
        self.hint_lbl.pack(fill="x", padx=6, pady=(4, 2))

        # scrollable area
        canvas = tk.Canvas(mid, height=220, highlightthickness=0)
        scroll = ttk.Scrollbar(mid, orient="vertical", command=canvas.yview)
        self.rows_frame = ttk.Frame(canvas)
        self.rows_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _build_footer(self):
        bot = ttk.Frame(self.root)
        bot.pack(fill="both", expand=True, padx=12, pady=(4, 12))

        ctrl = ttk.Frame(bot)
        ctrl.pack(fill="x")
        self.install_btn = ttk.Button(ctrl, text="Install / Update",
                                      command=self.start_install,
                                      state="disabled", style="Accent.TButton")
        self.install_btn.pack(side="left")
        self.progress = ttk.Progressbar(ctrl, mode="determinate",
                                        style="Accent.Horizontal.TProgressbar")
        self.progress.pack(side="left", fill="x", expand=True, padx=10)

        # Status line beneath the controls (always shows what's happening).
        self.status_var = tk.StringVar(value="Starting...")
        self.status_lbl = ttk.Label(bot, textvariable=self.status_var,
                                    style="Status.TLabel")
        self.status_lbl.pack(fill="x", pady=(6, 0))
        self._busy = False  # whether the progress bar is animating

        self.log = tk.Text(bot, height=11, wrap="word", state="disabled",
                          font=("Consolas", 9), background="#ffffff",
                          relief="solid", borderwidth=1,
                          highlightthickness=0)
        self.log.pack(fill="both", expand=True, pady=(8, 0))

    # ---------- logging via queue (thread-safe) ----------
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
            self.msg_queue.put(("status", f"Downloading {name} ({current}/{total})"))

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
                    # Switch to determinate for measurable per-file progress.
                    self._set_busy(False)
                    self.progress.configure(maximum=max(total, 1), value=cur)
                elif kind == "done":
                    self._on_install_done(payload)
                elif kind == "loaded":
                    self._on_manifest_loaded()
                elif kind == "java":
                    self._on_java_result(payload)
                elif kind == "load_error":
                    self._set_busy(False)
                    self.status_var.set("Failed to load pack.")
                    self.info_lbl.configure(
                        text=f"Failed to load pack: {payload}", foreground="#c62828")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _set_busy(self, on):
        """Toggle the indeterminate (animated) progress bar."""
        if on and not self._busy:
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
            self._busy = True
        elif not on and self._busy:
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self._busy = False

    # ---------- manifest loading ----------
    def load_manifest(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Manifest URL", "Please enter a manifest URL.")
            return
        self.info_lbl.configure(text="Loading pack info...", foreground="#555")
        self.install_btn.configure(state="disabled")
        self._busy_start()
        self._status("Connecting to server...")
        threading.Thread(target=self._load_worker, args=(url,), daemon=True).start()

    def _load_worker(self, url):
        try:
            eng = Engine(url)
            eng.load(log=self._log, status=self._status)
            self.engine = eng
            self.msg_queue.put(("loaded", None))
            # Java check spawns a subprocess (slow JVM cold start); run it here
            # on the worker thread so it never blocks the UI, then deliver the
            # result via the queue.
            jv = java_check.java_version()
            self.msg_queue.put(("java", jv))
        except Exception as e:  # noqa: BLE001 - surfaced to user
            self.msg_queue.put(("load_error", str(e)))

    def _on_manifest_loaded(self):
        self._set_busy(False)
        self.status_var.set("Ready. Choose launcher(s) and click Install / Update.")
        m = self.engine.manifest
        # Java line starts as "checking..." and is filled in by the ("java", ...)
        # message once the background check completes.
        self.info_lbl.configure(
            text=(f"{m.pack_name}   •   MC {m.minecraft}   •   Fabric "
                  f"{self.engine.loader_version}   •   pack updated "
                  f"{self._fmt_date(m.version)}\n"
                  f"Java: checking..."))
        self.title_lbl.configure(text=m.pack_name)

        # populate launcher rows (start unchecked; user explicitly selects).
        # Detected launchers are listed first, then the rest (each group keeps
        # registry order).
        for r in self.rows:
            r.frame.destroy()
        self.rows = []
        targets = self.engine.detect_targets()
        ordered = [t for t in targets if t.present] + \
                  [t for t in targets if not t.present]
        for target in ordered:
            self.rows.append(LauncherRow(self.rows_frame, target))
        self.install_btn.configure(state="normal")
        self._log("Ready. Choose launcher(s) and click Install / Update.")

    def _on_java_result(self, jv):
        if self.engine is None or self.engine.manifest is None:
            return
        m = self.engine.manifest
        jv = jv or "not found (your launcher likely bundles Java)"
        self.info_lbl.configure(
            text=(f"{m.pack_name}   •   MC {m.minecraft}   •   Fabric "
                  f"{self.engine.loader_version}   •   pack updated "
                  f"{self._fmt_date(m.version)}\n"
                  f"Java: {jv}"))

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
        self.progress.configure(value=0)
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
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    InstallerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
