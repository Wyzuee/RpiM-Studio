from __future__ import annotations

import os
import ssl
from pathlib import Path


def _certifi_bundle() -> str | None:
    """Return a bundled Mozilla CA file when certifi is available."""
    try:
        import certifi

        path = Path(certifi.where()).resolve()
        if path.is_file() and path.stat().st_size > 0:
            return str(path)
    except Exception:
        pass
    return None


def configure_tls_environment() -> str | None:
    """Make frozen Windows/macOS builds use a real CA bundle.

    Python/OpenSSL builds on macOS don't always inherit the certificates trusted
    by Safari/Keychain. A PyInstaller .app can therefore fail on perfectly valid
    HTTPS/WSS endpoints with CERTIFICATE_VERIFY_FAILED. Pointing OpenSSL and the
    HTTP clients at certifi's bundled Mozilla roots keeps verification enabled
    while making the result independent of the machine's Python installation.
    """
    bundle = _certifi_bundle()
    if not bundle:
        return None

    # SSL_CERT_FILE is consumed by OpenSSL / ssl.create_default_context(), which
    # is also what asyncio/websockets uses when connecting to a wss:// endpoint.
    os.environ["SSL_CERT_FILE"] = bundle

    # Keep requests/urllib3 and other common clients on the same trust bundle.
    os.environ["REQUESTS_CA_BUNDLE"] = bundle
    os.environ["CURL_CA_BUNDLE"] = bundle
    return bundle


def create_ssl_context() -> ssl.SSLContext:
    """Create a verification-enabled context using the same bundled CA roots."""
    bundle = _certifi_bundle()
    if bundle:
        return ssl.create_default_context(cafile=bundle)
    return ssl.create_default_context()


__all__ = ["configure_tls_environment", "create_ssl_context"]
