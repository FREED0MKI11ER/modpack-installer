"""ATLauncher.

Instances live under <ATLauncher>/instances/<Name>/ with an instance.json and
mods/ inside. The ATLauncher root is commonly:
  Windows: %APPDATA%\\ATLauncher
  macOS:   ~/Library/Application Support/ATLauncher
  Linux:   ~/.atlauncher  (or a portable dir next to the jar; user can browse)

ATLauncher's instance.json is a *merged Mojang + Fabric version manifest* at the
top level (id, javaVersion, arguments, assetIndex, assets, downloads, logging,
libraries, mainClass, ...) PLUS a `uuid` and a `launcher` metadata block. We
build that exact structure so ATLauncher's GSON parser accepts it. Mods are left
as an empty list in the launcher block - ATLauncher detects the jars we sync
into mods/ on disk and downloads vanilla + Fabric libraries itself on first
launch.
"""

import json
import os
import uuid as uuidlib

from .. import fabric
from .base import (Launcher, InstallResult, os_key, home,
                   appdata_roaming, safe_name)


class ATLauncher(Launcher):
    name = "ATLauncher"

    def _root(self):
        k = os_key()
        if k == "windows":
            return os.path.join(appdata_roaming(), "ATLauncher")
        if k == "macos":
            return os.path.join(home(), "Library", "Application Support",
                                "ATLauncher")
        # Linux: classic dotdir
        return os.path.join(home(), ".atlauncher")

    def default_path(self):
        return os.path.join(self._root(), "instances")

    def install(self, root, manifest, mc_version, loader_version,
                instance_name, log=None):
        log = log or (lambda *_: None)
        instances_dir = root
        os.makedirs(instances_dir, exist_ok=True)

        folder = safe_name(instance_name)
        inst_dir = os.path.join(instances_dir, folder)
        os.makedirs(os.path.join(inst_dir, "mods"), exist_ok=True)

        self._write_instance_json(
            inst_dir, instance_name, mc_version, loader_version, log)

        return InstallResult(
            launcher=self.name,
            game_dir=inst_dir,
            instance_name=instance_name,
            notes=("Open ATLauncher > Instances. If the instance doesn't show, "
                   "restart ATLauncher. Launch once to let it download "
                   "Minecraft and Fabric libraries."),
        )

    def _write_instance_json(self, inst_dir, instance_name, mc_version,
                            loader_version, log):
        log(f"Building Minecraft + Fabric manifest for {mc_version}...")
        version_manifest = fabric.build_merged_version(mc_version, loader_version)

        launcher_block = {
            "name": instance_name,
            "pack": "Minecraft",
            "description": instance_name,
            "packId": 0,
            "externalPackId": 0,
            "version": mc_version,
            "enableCurseForgeIntegration": True,
            "enableEditingMods": True,
            "loaderVersion": {
                "version": loader_version,
                "rawVersion": loader_version,
                "recommended": False,
                "type": "Fabric",
                "downloadables": {},
            },
            "requiredMemory": 0,
            "requiredPermGen": 0,
            "maximumMemory": 8192,  # 8 GB
            "quickPlay": {},
            "isDev": False,
            "isPlayable": True,
            "assetsMapToResources": False,
            "overridePaths": [],
            "checkForUpdates": True,
            "ignoredUpdates": [],
            "ignoreAllUpdates": False,
            "vanillaInstance": True,
            "lastPlayed": 0,
            "numPlays": 0,
            "mods": [],  # ATLauncher detects jars synced into mods/ on disk
        }

        # ATLauncher stores minimumLauncherVersion as a string; Mojang gives int.
        if "minimumLauncherVersion" in version_manifest:
            version_manifest["minimumLauncherVersion"] = str(
                version_manifest["minimumLauncherVersion"])

        # Top level = uuid + launcher block + the merged version manifest fields.
        data = {"uuid": str(uuidlib.uuid4()), "launcher": launcher_block}
        data.update(version_manifest)

        out = os.path.join(inst_dir, "instance.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        log(f"Wrote instance.json for '{instance_name}' "
            f"({len(version_manifest.get('libraries', []))} libraries)")
