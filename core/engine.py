"""High-level orchestration tying manifest, fabric, launchers, and sync together.

Typical flow used by the GUI:
    eng = Engine(manifest_url)
    eng.load()                      # fetch manifest, resolve fabric loader
    targets = eng.detect_targets()  # what launchers look installed
    eng.install(target, root_override=None, log=..., progress=...)
"""

from dataclasses import dataclass
from typing import Optional

from . import sync, fabric, servers
from .manifest import load_manifest, Manifest
from .launchers.registry import all_launchers
from .launchers.base import Launcher


@dataclass
class Target:
    launcher: Launcher
    detected_path: Optional[str]  # auto-detected root, or None

    @property
    def name(self):
        return self.launcher.name

    @property
    def present(self):
        return self.detected_path is not None


class Engine:
    def __init__(self, manifest_url):
        self.manifest_url = manifest_url
        self.manifest: Optional[Manifest] = None
        self.loader_version: Optional[str] = None
        self.targets = None

    def load(self, log=None, status=None):
        """Fetch manifest, resolve Fabric loader, and detect launchers.

        Fabric resolution (network) and launcher detection (filesystem) are run
        concurrently after the manifest is fetched, to cut startup time.

        Callbacks:
            log(message)     - verbose log lines
            status(text)     - short phase text for a status bar
        """
        import concurrent.futures

        log = log or (lambda *_: None)
        status = status or (lambda *_: None)

        status("Connecting to server...")
        log("Connecting to server...")
        self.manifest = load_manifest(self.manifest_url)
        log(f"Loaded pack '{self.manifest.pack_name}' "
            f"(version {self.manifest.version}, MC {self.manifest.minecraft})")

        # Run Fabric resolution (network) and launcher detection (disk) in
        # parallel; neither depends on the other.
        status("Resolving Fabric version and detecting launchers...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            fabric_future = ex.submit(
                fabric.resolve_loader_version,
                self.manifest.minecraft, self.manifest.fabric_loader)
            targets_future = ex.submit(self._detect_targets_now)
            self.loader_version = fabric_future.result()
            self.targets = targets_future.result()

        log(f"Fabric loader: {self.loader_version}")
        log(f"Detected {sum(1 for t in self.targets if t.present)} launcher(s).")
        status("Ready.")
        return self.manifest

    def _detect_targets_now(self):
        targets = []
        for ln in all_launchers():
            targets.append(Target(launcher=ln, detected_path=ln.detect()))
        return targets

    def detect_targets(self):
        # Return cached results from load() if available; else detect now.
        if self.targets is None:
            self.targets = self._detect_targets_now()
        return self.targets

    def install(self, target: Target, root_override=None, instance_name=None,
                log=None, progress=None):
        """Install/update the pack on a single launcher target."""
        if self.manifest is None:
            raise RuntimeError("Engine.load() must be called first")
        log = log or (lambda *_: None)

        root = root_override or target.detected_path or target.launcher.default_path()
        if not root:
            raise RuntimeError(
                f"No install location for {target.name}; please browse to it.")

        name = instance_name or self.manifest.pack_name

        log(f"== {target.name} ==")
        result = target.launcher.install(
            root=root,
            manifest=self.manifest,
            mc_version=self.manifest.minecraft,
            loader_version=self.loader_version,
            instance_name=name,
            log=log,
        )

        log(f"Syncing files into {result.game_dir}")
        summary = sync.run_sync(
            self.manifest, result.game_dir, log=log, progress=progress)

        # Add the server to the in-game server list, if configured.
        if self.manifest.server:
            try:
                servers.ensure_server(
                    result.game_dir, self.manifest.server.name,
                    self.manifest.server.ip, log=log)
            except Exception as e:  # noqa: BLE001 - non-fatal
                log(f"  could not update server list: {e}")

        result.notes = (result.notes + "\n" if result.notes else "") + (
            f"({summary['downloaded']} downloaded, "
            f"{summary['deleted']} removed)")
        return result
