"""Hash-diff sync engine.

Given a Manifest and a target game directory, ensure the managed directories
(e.g. mods/, shaderpacks/) exactly match the manifest:
  - download files that are missing or whose hash differs
  - delete files inside managed dirs that are not in the manifest

Re-running this is the auto-update mechanism.
"""

import hashlib
import os

from . import net
from .manifest import Manifest, ManifestFile


def _sha1_of(path, chunk=1024 * 1024):
    h = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(chunk), b""):
                h.update(block)
    except OSError:
        return None
    return h.hexdigest()


def _needs_download(dest, mf: ManifestFile):
    if not os.path.isfile(dest):
        return True
    if mf.size and os.path.getsize(dest) != mf.size:
        return True
    if mf.sha1:
        return _sha1_of(dest) != mf.sha1
    return False  # no hash to compare; assume present == ok


def plan_sync(manifest: Manifest, game_dir):
    """Return (to_download, to_delete) without making changes.

    to_download: list of ManifestFile
    to_delete:   list of absolute paths
    """
    to_download = []
    expected = set()
    for mf in manifest.files:
        dest = os.path.join(game_dir, mf.path.replace("/", os.sep))
        expected.add(os.path.normcase(os.path.abspath(dest)))
        if _needs_download(dest, mf):
            to_download.append(mf)

    to_delete = []
    for managed in manifest.managed_dirs:
        managed_path = os.path.join(game_dir, managed)
        if not os.path.isdir(managed_path):
            continue
        for root, _dirs, names in os.walk(managed_path):
            for name in names:
                full = os.path.abspath(os.path.join(root, name))
                if os.path.normcase(full) not in expected:
                    to_delete.append(full)
    return to_download, to_delete


def run_sync(manifest: Manifest, game_dir, log=None, progress=None):
    """Execute the sync. Callbacks:
        log(message)
        progress(current_index, total, filename)
    Returns dict summary.
    """
    log = log or (lambda *_: None)
    progress = progress or (lambda *_: None)

    to_download, to_delete = plan_sync(manifest, game_dir)
    total = len(to_download)

    if total == 0 and not to_delete:
        log("Already up to date.")
        return {"downloaded": 0, "deleted": 0, "uptodate": True}

    log(f"{total} file(s) to download, {len(to_delete)} to remove.")

    for i, mf in enumerate(to_download, start=1):
        dest = os.path.join(game_dir, mf.path.replace("/", os.sep))
        url = manifest.resolve_url(mf)
        progress(i, total, mf.path)
        log(f"[{i}/{total}] downloading {mf.path}")
        net.download_to(url, dest)
        # verify
        if mf.sha1:
            got = _sha1_of(dest)
            if got != mf.sha1:
                raise RuntimeError(
                    f"hash mismatch for {mf.path}: expected {mf.sha1}, got {got}")

    for path in to_delete:
        log(f"removing stale file {os.path.basename(path)}")
        try:
            os.remove(path)
        except OSError as e:
            log(f"  could not remove: {e}")

    log("Sync complete.")
    return {
        "downloaded": len(to_download),
        "deleted": len(to_delete),
        "uptodate": False,
    }
