"""Fabric loader resolution and installation for the vanilla launcher.

We use the Fabric meta API:
  - https://meta.fabricmc.net/v2/versions/loader/<mc>            -> list, [0] is recommended
  - https://meta.fabricmc.net/v2/versions/loader/<mc>/<loader>/profile/json
        -> a ready-to-use vanilla version JSON (inheritsFrom the base MC version)

For instance-based launchers (Prism, ATLauncher, etc.) we only need the
resolved loader *version string*; those launchers install Fabric themselves.
"""

import copy
import json
import os

from . import net, mojang

META = "https://meta.fabricmc.net/v2"


def get_profile_json(mc_version, loader_version):
    """Fetch the Fabric profile JSON (mainClass, jvm args, Fabric libraries)."""
    url = f"{META}/versions/loader/{mc_version}/{loader_version}/profile/json"
    return net.fetch_json(url)


def _maven_to_path(coord):
    """Convert a Maven coordinate to a repository path.

    'org.ow2.asm:asm:9.9' -> 'org/ow2/asm/asm/9.9/asm-9.9.jar'
    Supports an optional classifier: 'group:artifact:version:classifier'.
    """
    parts = coord.split(":")
    group = parts[0].replace(".", "/")
    artifact = parts[1]
    version = parts[2]
    classifier = parts[3] if len(parts) > 3 else None
    fname = f"{artifact}-{version}" + (f"-{classifier}" if classifier else "") + ".jar"
    return f"{group}/{artifact}/{version}/{fname}"


def _fabric_lib_to_mojang(lib):
    """Convert a Fabric meta library (Maven-style) into Mojang downloads.artifact
    form, matching what ATLauncher stores in instance.json.
    """
    name = lib["name"]
    repo = lib.get("url", "https://maven.fabricmc.net/").rstrip("/") + "/"
    path = _maven_to_path(name)
    artifact = {"path": path, "url": repo + path}
    if "sha1" in lib:
        artifact["sha1"] = lib["sha1"]
    if "size" in lib:
        artifact["size"] = lib["size"]
    return {"name": name, "downloads": {"artifact": artifact}}


def build_merged_version(mc_version, loader_version):
    """Build the merged Mojang + Fabric version manifest that ATLauncher embeds.

    Returns a dict containing the full vanilla version JSON with Fabric's
    mainClass, JVM arguments, and libraries layered on top.
    """
    base = copy.deepcopy(mojang.get_version_json(mc_version))
    profile = get_profile_json(mc_version, loader_version)

    # Fabric overrides the main class.
    base["mainClass"] = profile.get("mainClass", base.get("mainClass"))

    # Merge arguments: append Fabric's game/jvm args to Mojang's.
    base_args = base.setdefault("arguments", {})
    prof_args = profile.get("arguments", {}) or {}
    for key in ("game", "jvm"):
        if prof_args.get(key):
            base_args.setdefault(key, [])
            base_args[key] = base_args[key] + list(prof_args[key])

    # Prepend Fabric libraries (converted to Mojang artifact form) so the loader
    # is on the classpath. Order doesn't matter for resolution.
    fabric_libs = [_fabric_lib_to_mojang(l) for l in profile.get("libraries", [])]
    base["libraries"] = fabric_libs + base.get("libraries", [])

    return base


def resolve_loader_version(mc_version, requested="auto"):
    """Return a concrete Fabric loader version string.

    If requested != 'auto', it is returned as-is. Otherwise we pick the latest
    stable loader for the given MC version from the meta API.
    """
    if requested and requested != "auto":
        return requested
    data = net.fetch_json(f"{META}/versions/loader/{mc_version}")
    if not data:
        raise RuntimeError(f"No Fabric loader available for MC {mc_version}")
    # Prefer the first stable entry; the list is newest-first.
    for entry in data:
        if entry.get("loader", {}).get("stable"):
            return entry["loader"]["version"]
    return data[0]["loader"]["version"]


def fabric_version_id(mc_version, loader_version):
    return f"fabric-loader-{loader_version}-{mc_version}"


def install_into_vanilla(mc_dir, mc_version, loader_version, log=None):
    """Write the Fabric version JSON into <mc_dir>/versions/<id>/<id>.json.

    The vanilla launcher (and the dedicated profile) will then resolve the rest
    (libraries, base MC jar) on first launch via inheritsFrom.
    Returns the version id.
    """
    log = log or (lambda *_: None)
    version_id = fabric_version_id(mc_version, loader_version)
    url = f"{META}/versions/loader/{mc_version}/{loader_version}/profile/json"
    profile = net.fetch_json(url)
    # Ensure the id matches the folder name the launcher expects.
    profile["id"] = version_id

    version_dir = os.path.join(mc_dir, "versions", version_id)
    os.makedirs(version_dir, exist_ok=True)
    out = os.path.join(version_dir, version_id + ".json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
    log(f"Installed Fabric loader {loader_version} ({version_id})")
    return version_id
