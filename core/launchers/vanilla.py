"""Vanilla (official) Minecraft Launcher.

Layout:
  <mc_dir>/versions/<fabric-id>/<fabric-id>.json   (written by core.fabric)
  <mc_dir>/launcher_profiles.json                  (we add/update a profile)
  <mc_dir>/modpacks/<PackName>/                     (dedicated gameDir; mods here)

Using a dedicated gameDir avoids clobbering the player's existing mods in the
default .minecraft directory.
"""

import datetime
import json
import os

from .. import fabric
from .base import Launcher, InstallResult, os_key, home, appdata_roaming, safe_name


class VanillaLauncher(Launcher):
    name = "Minecraft Launcher (Vanilla)"
    self_installs_fabric = False  # we write the Fabric version JSON ourselves

    def default_path(self):
        k = os_key()
        if k == "windows":
            return os.path.join(appdata_roaming(), ".minecraft")
        if k == "macos":
            return os.path.join(home(), "Library", "Application Support", "minecraft")
        return os.path.join(home(), ".minecraft")

    def is_valid_root(self, path):
        """Require evidence the launcher is actually installed, not just an
        empty/leftover data folder.

        Accept if launcher_profiles.json exists in the data dir, OR (macOS) the
        Minecraft.app is present in /Applications.
        """
        if not path:
            return False
        if os.path.isfile(os.path.join(path, "launcher_profiles.json")):
            return True
        if os_key() == "macos" and os.path.isdir("/Applications/Minecraft.app"):
            return True
        return False

    def game_dir_for(self, root, instance_name):
        return os.path.join(root, "modpacks", safe_name(instance_name))

    def install(self, root, manifest, mc_version, loader_version,
                instance_name, log=None):
        log = log or (lambda *_: None)
        mc_dir = root

        # 1. Install Fabric version JSON into versions/
        version_id = fabric.install_into_vanilla(
            mc_dir, mc_version, loader_version, log=log)

        # 2. Dedicated game directory for the pack
        game_dir = self.game_dir_for(mc_dir, instance_name)
        os.makedirs(game_dir, exist_ok=True)

        # 3. Add/update profile in launcher_profiles.json
        self._write_profile(mc_dir, version_id, game_dir, instance_name, log)

        return InstallResult(
            launcher=self.name,
            game_dir=game_dir,
            instance_name=instance_name,
            notes=(f"Open the Minecraft Launcher, choose the '{instance_name}' "
                   f"profile, and click Play."),
        )

    def _write_profile(self, mc_dir, version_id, game_dir, instance_name, log):
        profiles_path = os.path.join(mc_dir, "launcher_profiles.json")
        data = {}
        if os.path.isfile(profiles_path):
            try:
                with open(profiles_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                log("warning: could not read launcher_profiles.json, creating new")
                data = {}
        data.setdefault("profiles", {})

        now = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z")
        key = "modpack_" + safe_name(instance_name).replace(" ", "_").lower()
        existing = data["profiles"].get(key, {})
        existing.update({
            "name": instance_name,
            "type": "custom",
            "lastVersionId": version_id,
            "gameDir": game_dir,
            "created": existing.get("created", now),
            "lastUsed": now,
            "icon": "Furnace",
        })
        data["profiles"][key] = existing

        # Preserve required top-level keys the launcher expects.
        data.setdefault("settings", {})
        data.setdefault("version", 3)

        with open(profiles_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        log(f"Added launcher profile '{instance_name}'")
