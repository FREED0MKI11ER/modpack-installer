"""Small HTTP helpers built on the stdlib (no third-party deps)."""

import json
import ssl
import urllib.parse
import urllib.request
import urllib.error

USER_AGENT = "ModpackInstaller/1.0 (+https://example.com)"
_TIMEOUT = 30


def encode_url(url):
    """Percent-encode unsafe characters (spaces, parens, etc.) in the path and
    query of a URL so urllib will accept it.

    Defensive: works even if a published manifest contains raw, unencoded
    characters. Already-encoded sequences (e.g. %20) are preserved.
    """
    parts = urllib.parse.urlsplit(url)
    # quote path but keep already-encoded triplets and the path separators.
    path = urllib.parse.quote(parts.path, safe="/%")
    query = urllib.parse.quote(parts.query, safe="=&%")
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, path, query, parts.fragment))


def _ssl_context():
    """Build an SSL context with a known-good CA bundle.

    On macOS (and frozen apps generally) Python may not find the system CA
    store, causing CERTIFICATE_VERIFY_FAILED. certifi ships Mozilla's CA bundle
    and works identically on every OS, bundled or not. Falls back to the default
    context if certifi is unavailable.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001 - fall back to system default
        return ssl.create_default_context()


def _opener():
    handler = urllib.request.HTTPSHandler(context=_ssl_context())
    return urllib.request.build_opener(handler)


def fetch_bytes(url, timeout=_TIMEOUT):
    """Download a URL and return raw bytes."""
    req = urllib.request.Request(encode_url(url),
                                 headers={"User-Agent": USER_AGENT})
    with _opener().open(req, timeout=timeout) as resp:
        return resp.read()


def fetch_text(url, timeout=_TIMEOUT, encoding="utf-8"):
    return fetch_bytes(url, timeout=timeout).decode(encoding)


def fetch_json(url, timeout=_TIMEOUT):
    return json.loads(fetch_text(url, timeout=timeout))


def download_to(url, dest_path, progress_cb=None, timeout=_TIMEOUT):
    """Stream a URL to dest_path. progress_cb(downloaded, total) optional.

    Writes to a temp file then atomically replaces dest_path.
    """
    import os
    import tempfile

    req = urllib.request.Request(encode_url(url),
                                 headers={"User-Agent": USER_AGENT})
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(dest_path))
    try:
        with _opener().open(req, timeout=timeout) as resp, \
                os.fdopen(tmp_fd, "wb") as out:
            total = int(resp.headers.get("Content-Length", 0) or 0)
            downloaded = 0
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                if progress_cb:
                    progress_cb(downloaded, total)
        os.replace(tmp_path, dest_path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
