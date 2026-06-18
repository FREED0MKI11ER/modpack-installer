"""Launcher writer interface and shared helpers.

Each launcher subclass knows how to:
  - detect()        : find default install path(s) on this OS
  - is_present()    : whether a default path exists
  - default_path()  : best-guess root the user can override/browse
  - install()       : create/update the instance/profile and return notes

The actual mod/shaderpack file sync is done by core.sync against the
`game_dir` each launcher exposes; launchers differ only in how they register
the instance/profile and where that game_dir lives.
"""

import os
import sys
import platform
from dataclasses import dataclass


def os_key():
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def home():
    return os.path.expanduser("~")


def appdata_roaming():
    """Windows %APPDATA% (Roaming)."""
    return os.environ.get("APPDATA") or os.path.join(
        home(), "AppData", "Roaming")


def appdata_local():
    return os.environ.get("LOCALAPPDATA") or os.path.join(
        home(), "AppData", "Local")


@dataclass
class InstallResult:
    launcher: str
    game_dir: str
    instance_name: str
    notes: str = ""


class Launcher:
    """Base class. Subclasses set `name` and implement the hooks."""

    name = "Launcher"
    # Whether this launcher installs Fabric itself (instance-based launchers)
    # or relies on us writing a vanilla version JSON.
    self_installs_fabric = True

    def candidate_paths(self):
        """Return a list of possible install roots, best-guess first.

        Default implementation wraps default_path(). Launchers that live in
        several possible locations should override this.
        """
        p = self.default_path()
        return [p] if p else []

    def is_valid_root(self, path):
        """Return True if `path` looks like a real install of this launcher.

        Override to check for a signature (e.g. instances/ or
        launcher_profiles.json) rather than just the folder existing. The
        default accepts any existing directory.
        """
        return bool(path) and os.path.isdir(path)

    def detect(self):
        """Return the first candidate path that looks like a real install."""
        for path in self.candidate_paths():
            if path and self.is_valid_root(path):
                return path
        return None

    def is_present(self):
        return self.detect() is not None

    def default_path(self):
        raise NotImplementedError

    def install(self, root, manifest, mc_version, loader_version,
                instance_name, log=None):
        """Create/update the instance under `root` and return InstallResult.

        Implementations should create the instance metadata, compute the
        game_dir, and leave file syncing to the caller (engine), OR call sync
        themselves. In this project the engine calls sync() after install()
        using InstallResult.game_dir.
        """
        raise NotImplementedError


def safe_name(name):
    """Sanitize a string for use as a folder name."""
    keep = "-_. "
    out = "".join(c for c in name if c.isalnum() or c in keep).strip()
    return out or "Modpack"
