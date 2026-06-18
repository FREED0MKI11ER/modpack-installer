"""Registry of all supported launchers.

Supported: Vanilla, Prism, MultiMC, ATLauncher. Modrinth App, GDLauncher, and
PolyMC were dropped since players don't use them.
"""

from .vanilla import VanillaLauncher
from .prism import PrismLauncher, MultiMCLauncher
from .atlauncher import ATLauncher


def all_launchers():
    """Return fresh instances of every supported launcher."""
    return [
        VanillaLauncher(),
        PrismLauncher(),
        MultiMCLauncher(),
        ATLauncher(),
    ]
