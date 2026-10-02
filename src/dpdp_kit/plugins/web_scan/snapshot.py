"""Load the target page once and capture what happens before any consent interaction."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from ...context import Context, PrerequisiteMissing
from .rules import host_matches

log = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
_ALLOWED_SCHEMES = ("http", "https")
_TRACKER_FIELDS = {"domain", "name", "category", "action"}


@dataclass(frozen=True)
class PageSnapshot:
    url: str
    final_url: str
    requests: list[dict[str, str]]
    cookies: list[dict[str, Any]]
    banner: dict[str, Any]
    screenshot: Path
    request_log: Path


@lru_cache(maxsize=1)
def banner_script() -> str:
    return (_HERE / "banner.js").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def trackers() -> list[dict[str, str]]:
    """The bundled tracker list. Raises ValueError if an entry is malformed (a packaging bug)."""
    with (_HERE / "trackers.yaml").open(encoding="utf-8") as fh:
        entries = yaml.safe_load(fh)
    for entry in entries:
        missing = _TRACKER_FIELDS - entry.keys()
        if missing or entry["action"] not in ("fail", "review"):
            raise ValueError(f"trackers.yaml: bad entry {entry!r} (missing {sorted(missing)} or invalid action)")
    return [{k: str(v) for k, v in e.items()} for e in entries]


def is_third_party(url: str, first_party: str) -> bool:
    host = urlsplit(url).hostname
    if not host:
        return False
    return not (host_matches(host, first_party) or host_matches(first_party, host))


def validate_url(url: str) -> str:
    """Accept only absolute http(s) URLs. Raises PrerequisiteMissing with the reason otherwise."""
    parts = urlsplit(url)
    if parts.scheme not in _ALLOWED_SCHEMES or not parts.hostname:
        raise PrerequisiteMissing(f"--url must be an absolute http(s) URL, got {url!r}")
    return url


def _scan_frames(page: Any) -> dict[str, Any]:
    script = banner_script()
    for frame in page.frames:  # main frame first
        try:
            found = frame.evaluate(script)
        except Exception as exc:  # detached or cross-origin-restricted frames are expected; keep scanning
            log.debug("banner scan failed in frame %s: %s", frame.url, exc)
            continue
        if isinstance(found, dict) and found.get("found"):
            return {**found, "frame_url": frame.url}
    return {"found": False}


def _request_record(request: Any) -> dict[str, str]:
    parts = urlsplit(request.url)
    return {"url": request.url, "host": parts.hostname or "", "path": parts.path, "type": request.resource_type}


def collect(ctx: Context) -> PageSnapshot:
    """Load ``ctx.target['url']`` once, without interacting, and record requests, cookies and the banner."""
    url = validate_url(ctx.require("url"))
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise PrerequisiteMissing(
            'Playwright is not installed. Run: pip install "dpdp-kit[web]" && playwright install chromium'
        ) from exc

    opts = ctx.options
    channel = opts.get("browser_channel")
    first_party = urlsplit(url).hostname or ""
    requests: list[dict[str, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel=channel) if channel else p.chromium.launch()
        try:
            context = browser.new_context(
                locale="en-IN", timezone_id="Asia/Kolkata", viewport={"width": 1366, "height": 900}
            )
            if opts.get("block_third_party"):
                # The "request" event fires before routing, so blocked requests are still recorded.
                context.route(
                    "**/*",
                    lambda route: (
                        route.abort() if is_third_party(route.request.url, first_party) else route.continue_()
                    ),
                )
            page = context.new_page()
            page.on("request", lambda r: requests.append(_request_record(r)))
            page.goto(url, wait_until="load", timeout=int(opts.get("timeout_ms", 45000)))
            page.wait_for_timeout(int(opts.get("settle_ms", 4000)))
            screenshot = ctx.write_evidence("web-scan-first-load.png", page.screenshot())
            banner = _scan_frames(page)
            cookies = [
                {"name": c["name"], "domain": c["domain"], "expires": c.get("expires")} for c in context.cookies()
            ]
            final_url = page.url
        finally:
            browser.close()

    request_log = ctx.write_evidence("web-scan-requests.json", json.dumps(requests, indent=2))
    return PageSnapshot(url, final_url, requests, cookies, banner, screenshot, request_log)
