"""Mojang version manifest helpers.

Used to fetch the full vanilla Minecraft version JSON, which ATLauncher embeds
(merged with Fabric) into its instance.json.
"""

from . import net

VERSION_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"


def get_version_json(mc_version):
    """Return the full Mojang version JSON for the given Minecraft version."""
    manifest = net.fetch_json(VERSION_MANIFEST)
    entry = next(
        (v for v in manifest.get("versions", []) if v.get("id") == mc_version),
        None)
    if entry is None:
        raise RuntimeError(
            f"Minecraft version {mc_version} not found in Mojang manifest")
    return net.fetch_json(entry["url"])
