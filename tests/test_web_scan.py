"""Integration tests: real Chromium against the fixture sites (third-party requests recorded but blocked)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dpdp_kit.context import Context
from dpdp_kit.models import Result, Status
from dpdp_kit.plugins.web_scan import checks

pytestmark = pytest.mark.browser

P, F, R = Status.PASS, Status.FAIL, Status.REVIEW
CHECKS = ("pre_consent_trackers", "reject_option_first_layer", "no_prechecked_toggles", "notice_link_in_banner")

# fixture site -> expected status per check, in CHECKS order. See fixtures/README.md.
EXPECTED = {
    "noncompliant": (F, F, F, F),
    "compliant": (P, P, P, P),
    "no-banner": (P, R, R, R),
    "shadow-dom": (P, P, F, P),
    "iframe": (P, F, P, F),
    "hindi": (P, P, P, P),
    "necessary-only": (P, P, P, P),
}


def scan(url: str, out_dir: Path, channel: str | None) -> dict[str, Result]:
    ctx = Context(
        out_dir=out_dir,
        target={"url": url},
        options={"browser_channel": channel, "block_third_party": True, "settle_ms": 300},
    )
    return {name: getattr(checks, name)(ctx, {}) for name in CHECKS}


@pytest.mark.parametrize("site", sorted(EXPECTED))
def test_fixture_site_expectations(site: str, fixture_server: str, browser_channel: str | None, tmp_path: Path) -> None:
    results = scan(f"{fixture_server}/{site}/", tmp_path, browser_channel)
    actual = tuple(results[name].status for name in CHECKS)
    details = {name: results[name].detail for name in CHECKS}
    assert actual == EXPECTED[site], details


def test_noncompliant_details_name_the_problem(
    fixture_server: str, browser_channel: str | None, tmp_path: Path
) -> None:
    results = scan(f"{fixture_server}/noncompliant/", tmp_path, browser_channel)
    assert "Meta Pixel" in results["pre_consent_trackers"].detail
    assert "Google Tag Manager" not in results["pre_consent_trackers"].detail  # loader alone is review-class
    assert "Marketing" in results["no_prechecked_toggles"].detail
    assert "Manage settings" in results["reject_option_first_layer"].detail


def test_accept_only_necessary_is_classed_as_reject(
    fixture_server: str, browser_channel: str | None, tmp_path: Path
) -> None:
    results = scan(f"{fixture_server}/necessary-only/", tmp_path, browser_channel)
    banner = results["reject_option_first_layer"].evidence[1].content
    assert banner["accept"] == ["Accept all cookies"]
    assert banner["reject"] == ["Accept only necessary"]


def test_iframe_banner_records_its_frame(fixture_server: str, browser_channel: str | None, tmp_path: Path) -> None:
    results = scan(f"{fixture_server}/iframe/", tmp_path, browser_channel)
    banner = results["no_prechecked_toggles"].evidence[1].content
    assert banner["frame_url"].endswith("/iframe/banner.html")


def test_page_loaded_once_and_evidence_saved(fixture_server: str, browser_channel: str | None, tmp_path: Path) -> None:
    results = scan(f"{fixture_server}/compliant/", tmp_path, browser_channel)
    assert (tmp_path / "evidence" / "web-scan-first-load.png").is_file()
    assert (tmp_path / "evidence" / "web-scan-requests.json").is_file()
    shots = {str(r.evidence[0].path) for r in results.values()}
    assert len(shots) == 1, "all checks must share one page load"


def test_relaxed_reject_rule_turns_fail_into_review(
    fixture_server: str, browser_channel: str | None, tmp_path: Path
) -> None:
    ctx = Context(
        out_dir=tmp_path,
        target={"url": f"{fixture_server}/noncompliant/"},
        options={"browser_channel": browser_channel, "block_third_party": True, "settle_ms": 300},
    )
    assert checks.reject_option_first_layer(ctx, {"require_first_layer_reject": False}).status is R


def test_unreachable_site_is_an_error_not_a_pass(browser_channel: str | None, tmp_path: Path) -> None:
    ctx = Context(
        out_dir=tmp_path,
        target={"url": "http://127.0.0.1:9/"},  # discard port: connection refused
        options={"browser_channel": browser_channel, "timeout_ms": 5000},
    )
    with pytest.raises(Exception, match=r"ERR_CONNECTION_REFUSED|ECONNREFUSED|net::"):
        checks.pre_consent_trackers(ctx, {})
