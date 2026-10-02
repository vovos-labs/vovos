"""Pure decision logic for web-scan checks.

Each function takes data captured from the page (requests, the detected banner)
and returns a status and message. No browser, I/O or clock, so every rule is
unit-testable in isolation.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from ...models import Status

NO_BANNER = (
    "No consent interface was detected. Either the site has none, or the detector missed it "
    "(closed shadow DOM, canvas, or labels it does not recognise). Check the screenshot."
)

Verdict = tuple[Status, str]


def host_matches(host: str, domain: str) -> bool:
    """True if ``host`` is ``domain`` or a subdomain of it (case-insensitive, trailing dot ignored)."""
    host = host.lower().rstrip(".")
    domain = domain.lower().rstrip(".")
    return bool(domain) and (host == domain or host.endswith("." + domain))


def match_trackers(
    requests: Iterable[Mapping[str, str]],
    trackers: Sequence[Mapping[str, str]],
    allow_domains: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Group requests that hit known tracker hosts, skipping allow-listed domains.

    Returns one entry per (tracker, host), with a request count and an example URL,
    sorted with blocking ('fail') trackers first.
    """
    hits: dict[tuple[str, str], dict[str, Any]] = {}
    for req in requests:
        host, path = req.get("host", ""), req.get("path", "")
        if any(host_matches(host, d) for d in allow_domains):
            continue
        tracker = next(
            (t for t in trackers if host_matches(host, t["domain"]) and path.startswith(t.get("path_prefix", ""))),
            None,
        )
        if tracker is None:
            continue
        hit = hits.setdefault(
            (tracker["name"], host),
            {
                "tracker": tracker["name"],
                "category": tracker["category"],
                "action": tracker["action"],
                "host": host,
                "requests": 0,
                "example": req.get("url", "")[:300],
            },
        )
        hit["requests"] += 1
    return sorted(hits.values(), key=lambda h: (h["action"] != "fail", h["tracker"], h["host"]))


def judge_trackers(hits: Sequence[Mapping[str, Any]], total_requests: int, known_hosts: int) -> Verdict:
    blocking = [h for h in hits if h["action"] == "fail"]
    if blocking:
        names = ", ".join(sorted({h["tracker"] for h in blocking}))
        return (
            Status.FAIL,
            f"{len(blocking)} tracking/advertising host(s) contacted before any consent interaction: {names}.",
        )
    if hits:
        names = ", ".join(sorted({h["tracker"] for h in hits}))
        return (
            Status.REVIEW,
            f"Only tag-manager/loader hosts contacted before consent ({names}). "
            "Confirm they do not fire tracking tags until consent is given.",
        )
    return (
        Status.PASS,
        f"None of {known_hosts} known tracker hosts were contacted before consent "
        f"({total_requests} requests observed). Hosts not on the list are not assessed; review the network log.",
    )


def judge_reject_option(banner: Mapping[str, Any], *, require_first_layer_reject: bool) -> Verdict:
    if not banner.get("found"):
        return Status.REVIEW, NO_BANNER
    accept, reject, settings = banner.get("accept", []), banner.get("reject", []), banner.get("settings", [])
    accept_label = repr(accept[0]) if accept else "an accept option"
    if reject:
        return Status.PASS, f"Decline option shown next to accept: {reject[0]!r} alongside {accept_label}."
    via = f" Declining appears to need the settings layer ({settings[0]!r})." if settings else ""
    status = Status.FAIL if require_first_layer_reject else Status.REVIEW
    return status, f"Accept ({accept_label}) is offered without an equally direct decline option.{via}"


def judge_prechecked(banner: Mapping[str, Any]) -> Verdict:
    if not banner.get("found"):
        return Status.REVIEW, NO_BANNER
    toggles = banner.get("toggles", [])
    prechecked = [t for t in toggles if t.get("checked") and not t.get("disabled")]
    if prechecked:
        labels = "; ".join(t.get("label") or "(unlabelled)" for t in prechecked)
        return Status.FAIL, f"{len(prechecked)} optional purpose(s) pre-selected: {labels}."
    if not toggles:
        return (
            Status.PASS,
            "No purpose toggles on the first layer, so nothing is pre-selected. Check the settings layer.",
        )
    return Status.PASS, f"{len(toggles)} purpose toggle(s) found; none pre-selected (locked/necessary toggles ignored)."


def judge_notice_link(banner: Mapping[str, Any]) -> Verdict:
    if not banner.get("found"):
        return Status.REVIEW, NO_BANNER
    links = banner.get("notice_links", [])
    if links:
        first = links[0]
        return Status.PASS, f"Consent interface links to a notice: {first.get('text') or first.get('href')!r}."
    return (
        Status.FAIL,
        "The consent interface does not link to a privacy notice, so consent is requested without the notice at hand.",
    )
