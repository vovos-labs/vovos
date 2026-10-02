"""Unit and property tests for the pure web-scan rules (no browser)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dpdp_kit.context import PrerequisiteMissing
from dpdp_kit.models import Status
from dpdp_kit.plugins.web_scan import rules
from dpdp_kit.plugins.web_scan.snapshot import is_third_party, trackers, validate_url

TRACKERS = [
    {"domain": "tracker.example", "name": "Tracker", "category": "analytics", "action": "fail"},
    {"domain": "tags.example", "name": "Loader", "category": "tag-manager", "action": "review"},
    {"domain": "social.example", "path_prefix": "/tr", "name": "Pixel", "category": "advertising", "action": "fail"},
]


def req(host: str, path: str = "/") -> dict[str, str]:
    return {"host": host, "path": path, "url": f"https://{host}{path}"}


# --- host matching --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("host", "domain", "expected"),
    [
        ("tracker.example", "tracker.example", True),
        ("a.b.tracker.example", "tracker.example", True),
        ("TRACKER.example.", "tracker.example", True),
        ("eviltracker.example", "tracker.example", False),  # suffix without a dot boundary
        ("tracker.example.evil", "tracker.example", False),
        ("", "tracker.example", False),
        ("tracker.example", "", False),
    ],
)
def test_host_matches(host: str, domain: str, expected: bool) -> None:
    assert rules.host_matches(host, domain) is expected


labels = st.from_regex(r"[a-z0-9]{1,10}", fullmatch=True)
domains = st.lists(labels, min_size=2, max_size=4).map(".".join)


@given(domain=domains, sub=labels)
def test_any_subdomain_matches_its_parent(domain: str, sub: str) -> None:
    assert rules.host_matches(f"{sub}.{domain}", domain)
    assert not rules.host_matches(domain, f"{sub}.{domain}")


# --- tracker matching ---------------------------------------------------------------------------


def test_match_groups_by_tracker_and_host_and_counts() -> None:
    hits = rules.match_trackers(
        [req("tracker.example"), req("tracker.example", "/x"), req("cdn.tracker.example")], TRACKERS
    )
    assert [(h["host"], h["requests"]) for h in hits] == [("cdn.tracker.example", 1), ("tracker.example", 2)]


def test_path_prefix_limits_matches() -> None:
    hits = rules.match_trackers([req("social.example", "/plugins/like"), req("social.example", "/tr")], TRACKERS)
    assert [h["example"] for h in hits] == ["https://social.example/tr"]


def test_allow_list_removes_domain_and_subdomains() -> None:
    hits = rules.match_trackers([req("tracker.example"), req("x.tracker.example")], TRACKERS, ["tracker.example"])
    assert hits == []


def test_blocking_trackers_sort_first() -> None:
    hits = rules.match_trackers([req("tags.example"), req("tracker.example")], TRACKERS)
    assert [h["action"] for h in hits] == ["fail", "review"]


request_strategy = st.fixed_dictionaries(
    {
        "host": st.one_of(domains, st.sampled_from(["tracker.example", "a.tags.example", ""])),
        "path": st.text(max_size=20),
    },
    optional={"url": st.text(max_size=50)},
)


@given(st.lists(request_strategy, max_size=30))
def test_match_never_crashes_and_counts_are_consistent(requests: list[dict[str, str]]) -> None:
    hits = rules.match_trackers(requests, TRACKERS)
    matched = sum(1 for r in requests if any(rules.host_matches(r["host"], t["domain"]) for t in TRACKERS[:2]))
    assert sum(h["requests"] for h in hits) >= matched
    assert all(h["requests"] >= 1 for h in hits)


@given(st.lists(request_strategy, max_size=30))
def test_allow_listing_every_tracker_yields_nothing(requests: list[dict[str, str]]) -> None:
    assert rules.match_trackers(requests, TRACKERS, [t["domain"] for t in TRACKERS]) == []


# --- verdicts --------------------------------------------------------------------------------------


def test_judge_trackers_branches() -> None:
    fail = {"tracker": "T", "action": "fail"}
    review = {"tracker": "L", "action": "review"}
    assert rules.judge_trackers([fail, review], 10, 5)[0] is Status.FAIL
    assert rules.judge_trackers([review], 10, 5)[0] is Status.REVIEW
    status, detail = rules.judge_trackers([], 10, 5)
    assert status is Status.PASS
    assert "not assessed" in detail  # a PASS must state its limits


BANNER = {
    "found": True,
    "accept": ["Accept all"],
    "reject": [],
    "settings": ["Manage"],
    "toggles": [],
    "notice_links": [],
}
NO_BANNER: dict[str, object] = {"found": False}


@pytest.mark.parametrize(
    "judge",
    [
        lambda b: rules.judge_reject_option(b, require_first_layer_reject=True),
        rules.judge_prechecked,
        rules.judge_notice_link,
    ],
)
def test_missing_banner_is_review_never_fail(judge) -> None:  # type: ignore[no-untyped-def]
    assert judge(NO_BANNER) == (Status.REVIEW, rules.NO_BANNER)


def test_reject_option() -> None:
    assert (
        rules.judge_reject_option({**BANNER, "reject": ["Reject all"]}, require_first_layer_reject=True)[0]
        is Status.PASS
    )
    status, detail = rules.judge_reject_option(BANNER, require_first_layer_reject=True)
    assert status is Status.FAIL
    assert "'Manage'" in detail
    assert rules.judge_reject_option(BANNER, require_first_layer_reject=False)[0] is Status.REVIEW


def test_reject_option_tolerates_missing_accept_list() -> None:
    status, _ = rules.judge_reject_option({"found": True, "reject": []}, require_first_layer_reject=True)
    assert status is Status.FAIL


@pytest.mark.parametrize(
    ("toggles", "expected"),
    [
        ([], Status.PASS),
        ([{"label": "Necessary", "checked": True, "disabled": True}], Status.PASS),
        ([{"label": "Analytics", "checked": False, "disabled": False}], Status.PASS),
        ([{"label": "Marketing", "checked": True, "disabled": False}], Status.FAIL),
        ([{"label": "", "checked": True}], Status.FAIL),
    ],
)
def test_prechecked(toggles: list[dict[str, object]], expected: Status) -> None:
    assert rules.judge_prechecked({**BANNER, "toggles": toggles})[0] is expected


def test_notice_link() -> None:
    linked = {**BANNER, "notice_links": [{"text": "", "href": "https://x.example/privacy"}]}
    status, detail = rules.judge_notice_link(linked)
    assert status is Status.PASS
    assert "x.example/privacy" in detail
    assert rules.judge_notice_link(BANNER)[0] is Status.FAIL


# --- input validation and bundled data -----------------------------------------------------------------


@pytest.mark.parametrize("url", ["https://example.com", "http://127.0.0.1:8080/path?q=1"])
def test_validate_url_accepts_http_urls(url: str) -> None:
    assert validate_url(url) == url


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "javascript:alert(1)", "example.com", "https://", "ftp://x.example"]
)
def test_validate_url_rejects_other_schemes(url: str) -> None:
    with pytest.raises(PrerequisiteMissing, match="http"):
        validate_url(url)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.shop.example/a.js", False),
        ("https://cdn.shop.example/a.js", False),
        ("https://tracker.example/p", True),
        ("data:image/png;base64,AAAA", False),
    ],
)
def test_is_third_party(url: str, expected: bool) -> None:
    assert is_third_party(url, "shop.example") is expected


def test_parent_domain_of_first_party_is_first_party() -> None:
    assert is_third_party("https://shop.example/x", "www.shop.example") is False


def test_bundled_tracker_list_is_well_formed() -> None:
    entries = trackers()
    keys = [(t["domain"], t.get("path_prefix", "")) for t in entries]
    assert len(keys) == len(set(keys)), "duplicate tracker entries"
    assert all(t["action"] in ("fail", "review") for t in entries)
    assert all(t["domain"] == t["domain"].lower() and "/" not in t["domain"] for t in entries)
