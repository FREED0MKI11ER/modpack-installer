#!/usr/bin/env python3
"""
generate_manifest.py - Admin tool to publish a modpack.

Scans a local pack directory (containing `mods/` and `shaderpacks/`),
computes hashes/sizes for every file, and writes `manifest.json`.

Usage:
    python generate_manifest.py --pack-dir ./pack --name "MyServerPack" \
        --mc 1.21.11 --base-url https://example.com/modpack/

Then upload the contents of --pack-dir (including the generated manifest.json)
to your static site so the files are reachable at:
    <base-url>/manifest.json
    <base-url>/mods/<file>.jar
    <base-url>/shaderpacks/<file>.zip

You can also produce a .mrpack with --mrpack for launchers that prefer importing.
"""

import argparse
import datetime
import hashlib
import json
import os
import sys
import urllib.parse
import zipfile

MANAGED_DIRS = ["mods", "shaderpacks", "resourcepacks"]


def hash_file(path):
    """Return (sha1, sha512, size) for a file, read once."""
    sha1 = hashlib.sha1()
    sha512 = hashlib.sha512()
    size = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha1.update(chunk)
            sha512.update(chunk)
            size += len(chunk)
    return sha1.hexdigest(), sha512.hexdigest(), size


def scan_pack(pack_dir, base_url):
    files = []
    base_url = base_url.rstrip("/") + "/" if base_url else ""
    for managed in MANAGED_DIRS:
        managed_path = os.path.join(pack_dir, managed)
        if not os.path.isdir(managed_path):
            continue
        for root, _dirs, names in os.walk(managed_path):
            for name in names:
                if name.startswith("."):
                    continue
                full = os.path.join(root, name)
                rel = os.path.relpath(full, pack_dir).replace(os.sep, "/")
                sha1, sha512, size = hash_file(full)
                # Percent-encode the path for the URL (spaces, parens, etc.)
                # while keeping `path` human-readable for local file placement.
                rel_encoded = urllib.parse.quote(rel, safe="/")
                files.append({
                    "path": rel,
                    "sha1": sha1,
                    "sha512": sha512,
                    "size": size,
                    "url": (base_url + rel_encoded) if base_url else rel_encoded,
                })
    files.sort(key=lambda f: f["path"])
    return files


def write_manifest(pack_dir, name, mc, fabric_loader, files,
                   server_name=None, server_ip=None):
    manifest = {
        "packName": name,
        "version": datetime.date.today().isoformat(),
        "minecraft": mc,
        "fabricLoader": fabric_loader,
        "managedDirs": MANAGED_DIRS,
        "files": files,
    }
    if server_ip:
        manifest["server"] = {
            "name": server_name or name,
            "ip": server_ip,
        }
    out = os.path.join(pack_dir, "manifest.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return out, manifest


def write_mrpack(pack_dir, manifest):
    """Emit a Modrinth .mrpack referencing the same file URLs.

    Note: some launchers enforce a download-domain allow-list and may reject
    self-hosted URLs. This is provided as a best-effort fallback/bonus.
    """
    index = {
        "formatVersion": 1,
        "game": "minecraft",
        "versionId": manifest["version"],
        "name": manifest["packName"],
        "dependencies": {
            "minecraft": manifest["minecraft"],
            "fabric-loader": manifest.get("fabricLoader", "auto"),
        },
        "files": [],
    }
    for f in manifest["files"]:
        if not f.get("url", "").startswith(("http://", "https://")):
            # mrpack requires absolute download URLs; skip if not absolute
            continue
        index["files"].append({
            "path": f["path"],
            "hashes": {"sha1": f["sha1"], "sha512": f["sha512"]},
            "downloads": [f["url"]],
            "fileSize": f["size"],
        })
    out = os.path.join(pack_dir, manifest["packName"] + ".mrpack")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("modrinth.index.json", json.dumps(index, indent=2))
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="Generate modpack manifest.json")
    p.add_argument("--pack-dir", required=True,
                   help="Local dir containing mods/ and shaderpacks/")
    p.add_argument("--name", required=True, help="Pack display name")
    p.add_argument("--mc", required=True, help="Minecraft version, e.g. 1.21.11")
    p.add_argument("--fabric-loader", default="auto",
                   help="Fabric loader version, or 'auto' to resolve live")
    p.add_argument("--base-url", default="",
                   help="Public base URL where files are hosted")
    p.add_argument("--server-name", default=None,
                   help="Display name for the server added to the in-game list")
    p.add_argument("--server-ip", default=None,
                   help="Server address (with :port if not 25565) to add to "
                        "the in-game server list")
    p.add_argument("--mrpack", action="store_true",
                   help="Also emit a .mrpack (requires absolute --base-url)")
    args = p.parse_args(argv)

    if not os.path.isdir(args.pack_dir):
        print(f"error: pack-dir not found: {args.pack_dir}", file=sys.stderr)
        return 1

    files = scan_pack(args.pack_dir, args.base_url)
    if not files:
        print("warning: no files found in mods/, shaderpacks/, resourcepacks/",
              file=sys.stderr)

    out, manifest = write_manifest(
        args.pack_dir, args.name, args.mc, args.fabric_loader, files,
        server_name=args.server_name, server_ip=args.server_ip)
    print(f"wrote {out} ({len(files)} files)")
    if args.server_ip:
        print(f"  server entry: {manifest['server']['name']} "
              f"-> {manifest['server']['ip']}")

    if args.mrpack:
        if not args.base_url.startswith(("http://", "https://")):
            print("error: --mrpack requires an absolute --base-url",
                  file=sys.stderr)
            return 1
        mrout = write_mrpack(args.pack_dir, manifest)
        print(f"wrote {mrout}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
