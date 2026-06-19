"""Prism Launcher / MultiMC / PolyMC (MMC-format launchers).

Instance layout:
  <instances>/<Name>/instance.cfg
  <instances>/<Name>/mmc-pack.json   (components: net.minecraft + fabric-loader)
  <instances>/<Name>/.minecraft/     (mods/, shaderpacks/ live here)

These launchers download Minecraft + Fabric libraries themselves on first
launch based on mmc-pack.json, so we only declare versions.
"""

import os

from .base import (Launcher, InstallResult, os_key, home,
                   appdata_roaming, appdata_local, safe_name)

FABRIC_UID = "net.fabricmc.fabric-loader"
MC_UID = "net.minecraft"


class PrismLauncher(Launcher):
    name = "Prism Launcher"
    folder_names = ["PrismLauncher"]

    def candidate_paths(self):
        candidates = []
        k = os_key()
        for n in self.folder_names:
            if k == "windows":
                candidates.append(os.path.join(appdata_roaming(), n, "instances"))
                candidates.append(os.path.join(appdata_local(), n, "instances"))
            elif k == "macos":
                candidates.append(os.path.join(
                    home(), "Library", "Application Support", n, "instances"))
            else:
                candidates.append(os.path.join(
                    home(), ".local", "share", n, "instances"))
                candidates.append(os.path.join(home(), "." + n.lower(), "instances"))
        return candidates

    def is_valid_root(self, path):
        """`path` is an instances/ dir; valid if it exists or its parent has an
        MMC-format config file."""
        if not path:
            return False
        if os.path.isdir(path):
            return True
        parent = os.path.dirname(path)
        for cfg in ("prismlauncher.cfg", "multimc.cfg", "metacache",
                    "accounts.json"):
            if os.path.isfile(os.path.join(parent, cfg)):
                return True
        return False

    def default_path(self):
        cands = self.candidate_paths()
        return cands[0] if cands else None

    def game_dir_for(self, root, instance_name):
        return os.path.join(root, safe_name(instance_name), ".minecraft")

    def install(self, root, manifest, mc_version, loader_version,
                instance_name, log=None):
        log = log or (lambda *_: None)
        instances_dir = root
        os.makedirs(instances_dir, exist_ok=True)

        dot_mc = self.game_dir_for(instances_dir, instance_name)
        inst_dir = os.path.dirname(dot_mc)
        os.makedirs(dot_mc, exist_ok=True)

        self._write_instance_cfg(inst_dir, instance_name, log)
        self._write_mmc_pack(inst_dir, mc_version, loader_version, log)

        return InstallResult(
            launcher=self.name,
            game_dir=dot_mc,
            instance_name=instance_name,
            notes=(f"Open {self.name}. The '{instance_name}' instance should "
                   f"appear (use 'Refresh' / restart if not). Launch it once to "
                   f"let it download Minecraft and Fabric."),
        )

    def _write_instance_cfg(self, inst_dir, instance_name, log):
        cfg = os.path.join(inst_dir, "instance.cfg")
        lines = {
            "InstanceType": "OneSix",
            "name": instance_name,
            "iconKey": "default",
        }
        # Preserve any existing keys we don't manage.
        if os.path.isfile(cfg):
            try:
                with open(cfg, "r", encoding="utf-8") as f:
                    for line in f:
                        if "=" in line:
                            k, v = line.rstrip("\n").split("=", 1)
                            lines.setdefault(k, v)
            except OSError:
                pass
        with open(cfg, "w", encoding="utf-8") as f:
            f.write("[General]\n")
            for k, v in lines.items():
                f.write(f"{k}={v}\n")
        log(f"Wrote instance.cfg for '{instance_name}'")

    def _write_mmc_pack(self, inst_dir, mc_version, loader_version, log):
        import json
        pack = {
            "formatVersion": 1,
            "components": [
                {"uid": MC_UID, "version": mc_version, "important": True},
                {"uid": FABRIC_UID, "version": loader_version},
            ],
        }
        with open(os.path.join(inst_dir, "mmc-pack.json"), "w",
                  encoding="utf-8") as f:
            json.dump(pack, f, indent=2)
        log(f"Wrote mmc-pack.json (MC {mc_version}, Fabric {loader_version})")


class MultiMCLauncher(PrismLauncher):
    name = "MultiMC"
    folder_names = ["MultiMC"]
    # MultiMC is often portable (instances next to the executable); detection
    # falls back to common per-OS spots, otherwise the user browses.
