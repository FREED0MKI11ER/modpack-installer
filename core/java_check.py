"""Light Java sanity check.

Minecraft launchers ship their own Java runtime, so this is purely
informational - we never block installation on it.
"""

import shutil
import subprocess


def find_java():
    """Return path to a `java` on PATH, or None."""
    return shutil.which("java")


def java_version():
    """Return a version string if java is found, else None."""
    java = find_java()
    if not java:
        return None
    try:
        out = subprocess.run(
            [java, "-version"],
            capture_output=True, text=True, timeout=10,
        )
        # `java -version` prints to stderr
        text = (out.stderr or out.stdout or "").strip()
        return text.splitlines()[0] if text else None
    except (OSError, subprocess.SubprocessError):
        return None
