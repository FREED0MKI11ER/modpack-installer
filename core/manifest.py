"""Fetch and represent the modpack manifest."""

from dataclasses import dataclass, field
from typing import List, Optional

from . import net


@dataclass
class ManifestFile:
    path: str          # e.g. "mods/sodium.jar"
    sha1: str
    sha512: str
    size: int
    url: str           # absolute, or relative to manifest base url

    @classmethod
    def from_dict(cls, d):
        return cls(
            path=d["path"],
            sha1=d.get("sha1", ""),
            sha512=d.get("sha512", ""),
            size=int(d.get("size", 0)),
            url=d["url"],
        )


@dataclass
class ServerEntry:
    name: str
    ip: str

    @classmethod
    def from_dict(cls, d):
        return cls(name=d.get("name", "Server"), ip=d["ip"])


@dataclass
class Manifest:
    pack_name: str
    version: str
    minecraft: str
    fabric_loader: str
    managed_dirs: List[str]
    files: List[ManifestFile] = field(default_factory=list)
    base_url: str = ""
    server: Optional[ServerEntry] = None

    @classmethod
    def from_dict(cls, d, base_url=""):
        server = None
        if d.get("server") and d["server"].get("ip"):
            server = ServerEntry.from_dict(d["server"])
        return cls(
            pack_name=d.get("packName", "Modpack"),
            version=d.get("version", ""),
            minecraft=d["minecraft"],
            fabric_loader=d.get("fabricLoader", "auto"),
            managed_dirs=d.get("managedDirs",
                               ["mods", "shaderpacks", "resourcepacks"]),
            files=[ManifestFile.from_dict(f) for f in d.get("files", [])],
            base_url=base_url,
            server=server,
        )

    def resolve_url(self, mf: ManifestFile) -> str:
        if mf.url.startswith(("http://", "https://")):
            return mf.url
        base = self.base_url.rstrip("/") + "/" if self.base_url else ""
        return base + mf.url.lstrip("/")


def load_manifest(manifest_url):
    """Fetch a manifest.json from a URL. base_url is derived from its location."""
    data = net.fetch_json(manifest_url)
    # base url = manifest url minus the final path segment
    base_url = manifest_url.rsplit("/", 1)[0]
    return Manifest.from_dict(data, base_url=base_url)
