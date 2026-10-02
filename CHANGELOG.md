# Changelog

All notable changes to the software and the control catalogue.

## [Unreleased]

### Software 0.1.0
- Engine: profiles with inheritance, organisation overlays (documented exclusions,
  overrides and extra controls), local and entry-point plugins.
- `web-scan` plugin: `pre_consent_trackers`, `reject_option_first_layer`,
  `no_prechecked_toggles`, `notice_link_in_banner`.
- `questionnaire` plugin with attestation records and an answers-file generator.
- JSON report (schema `dpdp-kit/report/v1`) and HTML report; SHA-256 hashes for evidence files.
- CLI: `validate`, `list`, `plugins`, `questionnaire`, `run` (`--fail-on` for CI).

- Quality gates: ruff (format and lint, including security rules), `mypy --strict`,
  pytest with branch coverage of at least 90% and warnings treated as errors,
  pip-audit, gitleaks; `scripts/check.py` runs them all; pre-commit hooks; CI on Linux and Windows.
- Web-scan decision logic moved to pure functions (`web_scan/rules.py`) and
  covered by table-driven and property-based tests.
- New fixtures: banner inside a shadow root, inside an iframe, Hindi labels, and
  "Accept only necessary" wording.
- `--url` now accepts only http(s) URLs; evidence file names cannot leave the evidence folder.

### Fixed
- `validate` crashed (undefined variable) when a questionnaire id lacked its control prefix.
- Evidence given as a relative path outside the report folder was neither hashed nor resolved correctly.
- A single string under `evidence:` in the answers file was split into characters.
- Malformed or missing answers files and invalid YAML now give a clear error instead of a traceback.
- Free-text answers containing Unicode spaces (e.g. NBSP) changed on every questionnaire regeneration.
- Test web server leaked its listening socket.

### Catalogue 2025.11-draft.1
- 25 draft controls covering notice, consent, withdrawal, security safeguards,
  breach intimation, retention, DPO contact, grievance redressal, Data Principal
  rights, children, Significant Data Fiduciaries and Consent Managers.
- All controls are `review_status: draft` pending legal review.
