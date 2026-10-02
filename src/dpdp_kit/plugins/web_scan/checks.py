"""web-scan checks: thin adapters between the page snapshot and the pure rules in :mod:`.rules`."""

from __future__ import annotations

from typing import Any

from ...context import Context
from ...models import Evidence, Result
from ...registry import check
from . import rules
from .snapshot import PageSnapshot, collect, trackers


def _snapshot(ctx: Context) -> PageSnapshot:
    snap: PageSnapshot = ctx.resource("web-scan.snapshot", collect)
    return snap


def _screenshot(snap: PageSnapshot) -> Evidence:
    return Evidence.screenshot("Page on first load, before any interaction", snap.screenshot)


def _banner_result(snap: PageSnapshot, verdict: rules.Verdict) -> Result:
    status, detail = verdict
    return Result(status, detail, [_screenshot(snap), Evidence.json("Detected consent interface", snap.banner)])


@check(
    "web-scan.pre_consent_trackers",
    description="Flags requests to known tracking/advertising hosts made before any consent interaction.",
)
def pre_consent_trackers(ctx: Context, params: dict[str, Any]) -> Result:
    snap = _snapshot(ctx)
    known = trackers()
    hits = rules.match_trackers(snap.requests, known, params.get("allow_domains") or [])
    status, detail = rules.judge_trackers(hits, len(snap.requests), len(known))
    evidence = [_screenshot(snap), Evidence.file("Full network log (first load)", snap.request_log)]
    if hits:
        evidence.append(Evidence.json("Tracker requests before consent", hits))
    return Result(status, detail, evidence)


@check(
    "web-scan.reject_option_first_layer",
    description="Checks that the consent interface offers a decline option alongside accept.",
)
def reject_option_first_layer(ctx: Context, params: dict[str, Any]) -> Result:
    snap = _snapshot(ctx)
    require = bool(params.get("require_first_layer_reject", True))
    return _banner_result(snap, rules.judge_reject_option(snap.banner, require_first_layer_reject=require))


@check(
    "web-scan.no_prechecked_toggles",
    description="Checks that optional purposes in the consent interface are not pre-selected.",
)
def no_prechecked_toggles(ctx: Context, params: dict[str, Any]) -> Result:
    snap = _snapshot(ctx)
    return _banner_result(snap, rules.judge_prechecked(snap.banner))


@check(
    "web-scan.notice_link_in_banner",
    description="Checks that the consent interface links to a privacy notice.",
)
def notice_link_in_banner(ctx: Context, params: dict[str, Any]) -> Result:
    snap = _snapshot(ctx)
    return _banner_result(snap, rules.judge_notice_link(snap.banner))
