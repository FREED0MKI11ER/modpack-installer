# Server Modpack Installer

A cross-platform GUI installer/updater for a self-hosted **Fabric** modpack.
Players pick which launcher(s) to install on; the app installs the correct
Fabric loader, creates a profile/instance, syncs your **mods**, **shaderpacks**,
and **resource packs** from a static website you host, and adds your server to
the in-game multiplayer list. Re-running it auto-updates.

- Minecraft: **1.21.11**, loader: **Fabric** (version resolved live)
- OS: **Windows, macOS, Linux**
- Players install nothing else (single bundled executable)
- Supported launchers: **Vanilla, Prism, MultiMC, ATLauncher**

---

## How it works

```
Your static site                      Player runs ModpackInstaller
├── manifest.json   <--- generated    1. reads manifest.json
├── mods/*.jar           by you       2. resolves + installs Fabric
└── shaderpacks/*.zip                 3. creates profile/instance
                                      4. syncs mods + shaderpacks (hash diff)
```

`manifest.json` lists every file with a SHA-1/SHA-512 + size. The installer
downloads only files that are missing or changed and removes files you've
deleted, so re-running it is the update mechanism.

---

## Part A — Admin guide (you)

### 1. Lay out your pack locally
```
pack/
├── mods/           # your .jar files
├── shaderpacks/    # optional .zip shader packs
└── resourcepacks/  # optional .zip texture/resource packs
```

### 2. Generate the manifest
```
python generate_manifest.py --pack-dir ./pack \
    --name "MyServerPack" --mc 1.21.11 \
    --base-url https://YOUR-SITE.example.com/modpack/ \
    --server-name "MyServer" --server-ip mc.example.com
```
- `--base-url` is the public URL where the files will live. The generator
  writes absolute URLs into the manifest so the installer can fetch them.
- `--fabric-loader auto` (default) makes the installer pick the latest stable
  Fabric loader for the MC version. Pin one with e.g. `--fabric-loader 0.19.3`.
- `--server-name` / `--server-ip` (optional) add your server to each player's
  in-game multiplayer list. Include `:port` in the IP only if not 25565.
- Add `--mrpack` to also emit a `.mrpack` (requires an absolute `--base-url`).
- Resource packs are synced and made available; players enable them in-game
  (Options > Resource Packs).

### 3. Upload
Upload the **contents of `pack/`** (including `manifest.json`) to your static
host so they are reachable at:
```
<base-url>/manifest.json
<base-url>/mods/<file>.jar
<base-url>/shaderpacks/<file>.zip
```
Any static host works: nginx/Apache serving a folder, GitHub Pages,
Cloudflare Pages, Netlify, etc. Files must be plain direct-download GETs
(no login wall).

> Note on Droppy: Droppy serves a directory as a single ZIP and individual
> files via short share links. This installer needs per-file direct URLs, so a
> plain static site (or Droppy share links pasted as each file's URL) is the
> way to go.

### 4. Point the installer at your manifest
Edit `config.json` **before building**:
```json
{
  "manifestUrl": "https://YOUR-SITE.example.com/modpack/manifest.json",
  "title": "My Server Modpack Installer"
}
```
Players can also paste/override the URL in the app, but setting it here means
they don't have to.

### 5. Build the player executable
**Windows:**
```
powershell -File build\build_windows.ps1
```
→ `dist\ModpackInstaller.exe`

**macOS / Linux:**
```
bash build/build_unix.sh
```
→ `dist/ModpackInstaller.app` (macOS) or `dist/ModpackInstaller` (Linux)

Build on each OS you want to support (PyInstaller does not cross-compile).
Distribute the single artifact to your players.

### Updating the pack later
Change files in `pack/`, re-run `generate_manifest.py`, re-upload. Players just
run the installer again — it syncs only what changed. You do **not** need to
rebuild the executable unless you change `config.json` or the app code.

---

## Part B — Player guide

1. Download **ModpackInstaller** from your server admin.
2. Run it.
   - **Windows SmartScreen:** click *More info → Run anyway* (the app is
     unsigned).
   - **macOS Gatekeeper:** right-click the app → *Open* the first time.
3. It shows the pack info and a list of launchers. Detected launchers are
   pre-ticked. Tick the launcher(s) you want; use **Browse** if your launcher
   wasn't auto-detected or lives in a custom folder.
4. Click **Install / Update**.
5. Open your launcher, select the new profile/instance, and play.
   - **ATLauncher / Prism / MultiMC:** if the instance doesn't appear, restart
     the launcher. Launch once to let it download Minecraft + Fabric libraries.

To update after the server changes the pack, just run the installer again.

---

## Project layout
```
modpack_installer/
├── installer.py            # GUI entry point
├── generate_manifest.py    # admin tool: build manifest.json (+ optional .mrpack)
├── config.json             # manifestUrl + title (set before building)
├── core/
│   ├── net.py              # stdlib HTTP helpers
│   ├── manifest.py         # fetch/parse manifest
│   ├── sync.py             # hash-diff download/remove engine
│   ├── fabric.py           # Fabric meta API + vanilla install
│   ├── java_check.py       # informational Java check
│   ├── mojang.py           # Mojang version manifest (for ATLauncher instance)
│   ├── nbt.py              # minimal NBT reader/writer
│   ├── servers.py          # adds server to servers.dat (in-game list)
│   ├── engine.py           # orchestration
│   └── launchers/          # one writer per launcher + registry
├── gui/app.py              # tkinter UI
└── build/                  # PyInstaller spec, build scripts, make_icon.py
```

## Notes & limitations
- **Auto-update** = re-running the installer (fast no-op when nothing changed).
  No launcher-specific launch hooks are used, for consistency across launchers.
- **ATLauncher** instances embed a full merged Minecraft + Fabric version
  manifest in `instance.json`; the installer builds this from the Mojang and
  Fabric meta APIs. The launcher downloads the actual game/library files on
  first launch.
- **Server list**: the installer merges your server into each game directory's
  `servers.dat` (uncompressed NBT), preserving any servers the player already
  has and de-duplicating by address.
- **Resource packs** are synced and available; players enable them in-game.
- **App icon** is generated at build time by `build/make_icon.py` (purple "FS"
  badge) using Pillow. Pillow is a build-time-only dependency and is **not**
  shipped in the player executable. Replace `build/icon.ico`/`icon.png` to
  customize.
- **Code signing** is not included; unsigned binaries trigger OS warnings that
  players click through.
