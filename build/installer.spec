# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the modpack installer.
# Build from the project root (modpack_installer/) with:
#     pyinstaller build/installer.spec
#
# Produces a single-file GUI executable that bundles config.json.
# On macOS it additionally produces a .app bundle (onedir).

import os
import sys

IS_MACOS = sys.platform == "darwin"

block_cipher = None

# The spec lives in build/, but the app sources live in the project root
# (one level up). Resolve paths relative to the project root.
ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))

# Bundle config.json alongside the app so core.config can find it.
datas = [(os.path.join(ROOT, "config.json"), ".")]

# Bundle the icon (for the runtime window/taskbar icon) if present.
ICON_ICO = os.path.join(ROOT, "build", "icon.ico")
ICON_PNG = os.path.join(ROOT, "build", "icon.png")
if os.path.isfile(ICON_ICO):
    datas.append((ICON_ICO, "."))
if os.path.isfile(ICON_PNG):
    datas.append((ICON_PNG, "."))
EXE_ICON = ICON_ICO if os.path.isfile(ICON_ICO) else None

a = Analysis(
    [os.path.join(ROOT, "installer.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if IS_MACOS:
    # onedir build so it can be wrapped into a proper .app bundle.
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="ModpackInstaller",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=EXE_ICON,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        name="ModpackInstaller",
    )
    app = BUNDLE(
        coll,
        name="ModpackInstaller.app",
        icon=EXE_ICON,
        bundle_identifier="com.yourserver.modpackinstaller",
    )
else:
    # Windows / Linux: single-file executable.
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="ModpackInstaller",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        runtime_tmpdir=None,
        console=False,  # GUI app: no console window
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=EXE_ICON,  # set to an .ico/.icns path if you have one
    )
