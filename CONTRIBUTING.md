# Contributing

Thank you for helping. Contributions from lawyers, privacy professionals,
auditors and developers are all welcome.

## Ways to help

| You are... | You could... |
|---|---|
| A lawyer or privacy practitioner | Review draft controls, open Interpretation RFCs, write interpretation notes |
| A developer | Write checks and plugins, improve detection, add fixtures |
| Running the kit on real sites | Report false positives and negatives with a minimal fixture that reproduces them |
| Fluent in an Indian language | Add consent-banner phrases to `banner.js`, translate questions and reports |

## Ground rules

- **Cite the law.** Every control cites the Section, Rule or Schedule it derives
  from. Interpretation goes in `interpretation.note`, not in the description.
- **Honest wording.** A check reports `PASS` only when it actually looked and found
  no gap. When it cannot tell, it returns `REVIEW`. When it cannot run, it raises
  `PrerequisiteMissing`. Never claim compliance.
- **Tests with every check.** Add a fixture under `fixtures/sites/` that makes the
  check pass and one that makes it fail.
- **No vendor promotion.** Do not add controls, checks or documentation that
  favour a product. See [GOVERNANCE.md](GOVERNANCE.md).
- **No personal data in fixtures or issues.** Use invented names and example domains.

## Developer setup

```bash
git clone <repo-url> && cd dpdp-kit
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
playwright install chromium        # or set DPDP_KIT_BROWSER_CHANNEL=chrome
pre-commit install                 # format, lint and secret scan on every commit
python scripts/check.py            # every gate CI runs; add --fast to skip browser tests and audit
```

The gates are ruff format, ruff lint, `mypy --strict`, `dpdp-kit validate`, and
pytest with branch coverage of at least 90%. Warnings are errors, so a leaked
socket or deprecated call fails the build. There is also a dependency audit.
Browser tests are marked `browser`. Skip them locally with `pytest -m "not browser"`;
CI always runs them.

Each phase of work starts with a test plan in `docs/test-plans/` (see
[phase 1](docs/test-plans/phase-1-core.md)). New detectors need a fixture that
must pass and one that must fail. Bug fixes start with a failing regression test.

## Developer Certificate of Origin

Every commit must be signed off to certify that you wrote it or have the right
to submit it under the project's licences ([DCO 1.1](https://developercertificate.org/)):

```bash
git commit -s -m "Add withdrawal parity check"
```

Contributions to `catalogue/` and `profiles/` are licensed under CC-BY-4.0.
Everything else is licensed under Apache-2.0. You keep your copyright; no
rights are assigned to any company.

## Pull request checklist

- [ ] `pytest` and `dpdp-kit validate` pass
- [ ] New or changed controls cite their legal source and keep `review_status: draft`
      unless a legal reviewer has signed off in the PR
- [ ] Changes to what a control means link to an Interpretation RFC
- [ ] New checks have passing and failing fixtures
- [ ] `CHANGELOG.md` updated
- [ ] Commits are signed off (`-s`)
