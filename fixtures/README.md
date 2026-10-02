# Fixtures

Small static websites with known, deliberate behaviour. The test suite serves
them on `127.0.0.1` and runs the web-scan checks against them, with third-party
requests recorded but blocked, so tests never contact real trackers.

| Site | Expected result |
|---|---|
| `sites/noncompliant` | trackers before consent (FAIL), no decline option (FAIL), pre-selected purpose (FAIL), no notice link (FAIL) |
| `sites/compliant` | PASS on all four web-scan checks |
| `sites/no-banner` | trackers PASS; banner checks REVIEW (nothing to inspect) |

When you add a check, add a fixture that makes it pass and one that makes it
fail. When you fix a false positive or negative found on a real website, add a
minimal fixture that reproduces it.
