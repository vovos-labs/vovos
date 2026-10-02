# Test plan — Phase 1: engine, catalogue, web-scan, questionnaire, reports

**Scope:** control catalogue and schemas, profile/overlay resolution, plugin
registry and loading, the engine and result roll-up, the `web-scan` and
`questionnaire` plugins, JSON/HTML reports, and the CLI.

**Risks, in priority order**
1. *False assurance:* a gap reported as PASS. This is the worst outcome for a compliance tool.
2. *False accusation:* a conforming site reported as FAIL, which destroys trust in the kit.
3. *Untrusted content in reports:* page text from a scanned site executes as script in the HTML report (XSS).
4. *Silent misconfiguration:* a typo in an overlay or answers file is ignored instead of reported.
5. *Evidence integrity:* evidence missing, unhashed, or pointing at the wrong file.
6. *Contract drift:* `report.json` no longer matches its published schema.

| Level | What | Where |
|---|---|---|
| Unit | Roll-up truth table plus properties (FAIL dominance, order independence) | `test_engine.py` |
| Unit | Web rules: host matching, tracker grouping and allow-list (table and property tests), each verdict branch | `test_web_rules.py` |
| Unit | Questionnaire: every answer branch, YAML booleans, scalar answers, string evidence, template round-trip (property) | `test_questionnaire.py` |
| Unit | Profiles: inheritance, overlay merge, reasons required, cycles, typo warnings | `test_profiles.py` |
| Unit | Catalogue: schema, file/id match, duplicates, invalid YAML, missing directories | `test_catalogue.py` |
| Unit | Context: evidence path sanitisation (traversal), resource caching | `test_context.py` |
| Unit | Registry: key and kind validation, duplicate keys, broken plugins reported, not raised | `test_registry.py` |
| Contract | Every report validates against `report.schema.json`, including every status | `test_report.py` |
| Security | HTML report escapes hostile page text; URL scheme allow-list; evidence names cannot escape the folder | `test_report.py`, `test_web_rules.py`, `test_context.py` |
| Integration | Real Chromium against fixture sites: noncompliant, compliant, no banner, shadow DOM, iframe, Hindi, "accept only necessary" | `test_web_scan.py` |
| End-to-end | CLI: validate, list, plugins, questionnaire, run; exit codes; malformed inputs; example overlay and plugin | `test_cli.py` |

**Out of scope for this phase:** real third-party websites (non-deterministic,
so they are covered by manual exploratory runs), performance (a single page
load), and the planned plugins (`doc-analyze`, `api-probe`).

**Exit criteria:** ruff, ruff format, `mypy --strict`, all tests (including
browser tests), branch coverage of at least 90%, and `dpdp-kit validate` all green.
