#!/usr/bin/env python3
"""Entry point for the modpack installer GUI."""

import os
import sys

# Ensure the package root is importable whether run from source or frozen.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.app import main  # noqa: E402

if __name__ == "__main__":
    main()
