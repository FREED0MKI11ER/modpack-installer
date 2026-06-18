# Build the Windows installer executable.
# Run from the project root: powershell -File build\build_windows.ps1
# Requires: Python 3 + pip. Installs pyinstaller into a local venv.

$ErrorActionPreference = "Stop"

# Create/activate a build venv to keep things clean.
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
# Pillow is build-time only (icon generation); not bundled into the exe.
& ".venv\Scripts\python.exe" -m pip install --upgrade pip pyinstaller Pillow

# Generate the app icon (build/icon.ico + icon.png).
& ".venv\Scripts\python.exe" build\make_icon.py

# Build using the spec (bundles config.json + icon, no console window).
& ".venv\Scripts\pyinstaller.exe" --noconfirm build\installer.spec

Write-Host ""
Write-Host "Done. Executable is at: dist\ModpackInstaller.exe"
Write-Host "Distribute that single .exe to your players."
