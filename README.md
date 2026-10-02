# DPDP Self-Test Kit

**An open-source kit that lets an organisation check its own practices against
India's Digital Personal Data Protection Act, 2023 and DPDP Rules, 2025, and see
where the gaps are.**

It runs on your own machine against your own systems. It sends nothing anywhere,
ranks nobody and certifies nothing. Every rule it applies is a readable YAML file
that anyone can inspect, challenge or improve.

> **This is a self-assessment aid, not legal advice and not a certification.**
> A clean report means the kit's checks found no gap, not that you are compliant.
> The control catalogue is a **draft** that has not yet been legally reviewed. See [DISCLAIMER.md](DISCLAIMER.md).

## What it does

```
 controls (YAML)  ──►  profile + your overlay  ──►  checks (plugins)  ──►  report (JSON + HTML)
 Act + Rules as        pick what applies,          web-scan,               gaps, evidence,
 testable rules        document exceptions         questionnaire, yours    SHA-256 hashes
```

- **Automated website checks** (`web-scan`): loads your site in a real browser
  without clicking anything and records whether trackers fire before consent,
  whether a decline option sits next to accept, whether purposes are pre-selected,
  and whether the banner links to a notice. A screenshot and the full network log
  are kept as evidence.
- **Attestation questionnaire** (`questionnaire`): for what software cannot see,
  such as breach procedures, retention and processor contracts. Each answer
  records who attested it, when, and which evidence supports it.
- **Profiles** for different kinds of Data Fiduciary: `base`, `sme`, `sdf`,
  `children`, `government` and `consent-manager`.
- **Your own rules**: add internal controls and checks without forking the project.

## Quick start

```bash
pip install "dpdp-kit[web]"        # from a checkout: pip install -e ".[dev]"
playwright install chromium        # or pass --browser-channel chrome later

dpdp-kit list --profile base                       # what will be assessed
dpdp-kit questionnaire --profile base -o answers.yaml   # fill this in
dpdp-kit run --profile base --url https://www.example.com \
             --answers answers.yaml --name "Example Ltd" --open
```

The report is written to `dpdp-report/`: `report.html` for people and
`report.json` (schema: `src/dpdp_kit/schemas/report.schema.json`) for other tools.

Use it in CI so regressions surface before release:

```bash
dpdp-kit run --url https://staging.example.com --fail-on high --format json
```

## How results are worded

| Status | Meaning |
|---|---|
| `FAIL` | A gap was found. Evidence is attached. |
| `REVIEW` | Inconclusive; a person needs to look. |
| `PASS` | The automated check found no gap. This does **not** prove compliance. |
| `ATTESTED` | A named person confirmed it in the questionnaire. |
| `NOT TESTED` | Nothing could run (no URL, question unanswered, plugin missing). |
| `N/A` | Excluded by your profile or overlay, with the reason shown. |

The kit never prints "compliant". See [docs/results.md](docs/results.md) for how
results roll up from individual checks to a control.

## Adapting it to your organisation

Create an overlay (see [examples/local-overlay.example.yaml](examples/local-overlay.example.yaml)):

```yaml
exclude:
  DPDP-NOT-003: "Internal portal; legal opinion LEG-2026-04."   # reason required
overrides:
  DPDP-CON-003:
    params: { web-scan.reject_option_first_layer: { require_first_layer_reject: false } }
    reason: "Legal opinion LEG-17 on Section 6(1)."
extra_controls: [our-controls]        # your own YAML controls (own id prefix)
```

```bash
dpdp-kit run --overlay our-overlay.yaml --plugins-dir our-plugins ...
```

Every exclusion and override appears in the report, so nothing is hidden from a reviewer.

## Repository layout

| Path | Contents | Licence |
|---|---|---|
| `catalogue/controls/` | One YAML file per control, with legal citation and interpretation note | CC-BY-4.0 |
| `catalogue/schema/` | JSON Schemas for controls, profiles and catalogue metadata | CC-BY-4.0 |
| `profiles/` | Built-in profiles | CC-BY-4.0 |
| `src/dpdp_kit/` | Engine, CLI, built-in plugins, report templates | Apache-2.0 |
| `fixtures/sites/` | Websites built to pass or fail on purpose, used by the tests | Apache-2.0 |
| `examples/` | Answers file, overlay, organisation control and plugin | Apache-2.0 |

## Contributing

The project needs lawyers and privacy practitioners as much as developers.

- **Improve a control or argue an interpretation**: open an
  [Interpretation RFC](.github/ISSUE_TEMPLATE/interpretation-rfc.yml).
- **Add a control**: see [docs/writing-a-control.md](docs/writing-a-control.md).
- **Add a check or plugin**: see [docs/writing-a-plugin.md](docs/writing-a-plugin.md).
- **Add tracker hosts or banner phrases** (especially in Indian languages):
  edit `src/dpdp_kit/plugins/web_scan/trackers.yaml` or `banner.js`, and add a fixture.

Read [CONTRIBUTING.md](CONTRIBUTING.md) and [GOVERNANCE.md](GOVERNANCE.md) first.

## Roadmap

- `doc-analyze`: check privacy notices against Rule 3 (optional AI assistance,
  bring your own key or a local model; output always marked REVIEW)
- `web-scan.withdrawal_parity`: compare the steps needed to give and to withdraw consent
- `api-probe`: consent-artefact lifecycle and withdrawal-propagation tests for CMPs and Consent Managers
- `config`: read exported cloud and logging configuration for Rule 6 safeguards
- GitHub Action, OSCAL export of the catalogue, Hindi and regional-language report output
