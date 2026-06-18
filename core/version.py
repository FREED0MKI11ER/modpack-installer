"""Application version.

Defaults to "dev" for local builds. CI overwrites APP_VERSION with the git tag
(e.g. "v1.0.2") before building a release.
"""

APP_VERSION = "dev"
