"""Load installer configuration (manifest URL, title).

Looks for config.json next to the executable / project root. When frozen by
PyInstaller, files bundled with --add-data land in sys._MEIPASS.
"""

import json
import os
import sys


def _candidate_dirs():
    dirs = []
    # 1. Next to the executable (frozen) or this file (source)
    if getattr(sys, "frozen", False):
        dirs.append(os.path.dirname(sys.executable))
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            dirs.append(meipass)
    # Project root (parent of the `core` package)
    dirs.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return dirs


def load_config():
    cfg = {
        "manifestUrl": "",
        "title": "Modpack Installer",
    }
    for d in _candidate_dirs():
        path = os.path.join(d, "config.json")
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg.update(json.load(f))
                break
            except (OSError, json.JSONDecodeError):
                continue
    return cfg
