#!/usr/bin/env bash
# Build the macOS / Linux installer.
# Run from the project root:  bash build/build_unix.sh
# Requires: python3 + pip.

set -euo pipefail

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
# Pillow is build-time only (icon generation). certifi ships the CA bundle and
# IS bundled into the app (needed for HTTPS cert verification, esp. on macOS).
python -m pip install --upgrade pip pyinstaller Pillow certifi

# Generate the app icon (build/icon.ico + icon.png).
python build/make_icon.py

pyinstaller --noconfirm build/installer.spec

echo ""
if [ "$(uname)" = "Darwin" ]; then
  echo "Done. App bundle is at: dist/ModpackInstaller.app"
  echo "Note: unsigned apps need right-click > Open the first time (Gatekeeper)."
else
  echo "Done. Executable is at: dist/ModpackInstaller"
  echo "Make it executable if needed: chmod +x dist/ModpackInstaller"
fi
