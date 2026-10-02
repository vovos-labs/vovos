from __future__ import annotations

import functools
import http.server
import os
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from dpdp_kit.registry import load_plugins

ROOT = Path(__file__).resolve().parents[1]
SITES = ROOT / "fixtures" / "sites"

load_plugins()


@pytest.fixture(scope="session")
def fixture_server() -> Iterator[str]:
    """Serve fixtures/sites on 127.0.0.1 and yield the base URL."""

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

    handler = functools.partial(Quiet, directory=str(SITES))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@functools.cache
def _browser_channel() -> str | None:
    """Return a launchable channel ('' for bundled Chromium), or None if none works.

    Set DPDP_KIT_BROWSER_CHANNEL to force one (e.g. 'chrome').
    """
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    forced = os.environ.get("DPDP_KIT_BROWSER_CHANNEL")
    candidates = [forced] if forced is not None else ["", "chrome", "msedge"]
    with sync_playwright() as p:
        for channel in candidates:
            try:
                browser = p.chromium.launch(channel=channel) if channel else p.chromium.launch()
            except PlaywrightError:
                continue
            browser.close()
            return channel
    return None


@pytest.fixture(scope="session")
def browser_channel() -> str | None:
    channel = _browser_channel()
    if channel is None:
        pytest.skip("no Playwright-launchable Chromium; run 'playwright install chromium'")
    return channel or None
