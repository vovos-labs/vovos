# Writing a control

A control is one testable requirement, in one YAML file under
`catalogue/controls/<area>/`, named after its id. The schema is
`catalogue/schema/control.schema.json`. Run `dpdp-kit validate` after editing.

```yaml
id: DPDP-CON-004                    # DPDP-<AREA>-<NNN>; file must be DPDP-CON-004.yaml
title: Withdrawing consent is as easy as giving it
description: >                      # what must be true, in plain language; no interpretation here
  The Data Principal can withdraw consent at any time, with ease comparable to
  the ease with which consent was given.
citation:
  act: ["Section 6(4)"]
  rules: []
  schedules: []
severity: high                      # critical | high | medium | low
tags: [base]                        # profiles select by tag
test_methods:                       # at least one; automated first, questionnaire as fallback
  - plugin: questionnaire
    check: ask
    params:
      id: DPDP-CON-004.q1           # must start with the control id
      question: >
        Can a Data Principal withdraw consent ... ?
      expect: "yes"
      help: Optional guidance shown in the answers file.
interpretation:
  confidence: medium                # high | medium | contested
  note: >
    Why the test is a fair proxy for the legal requirement, and what it does not cover.
  rfc: https://github.com/<org>/<repo>/issues/123   # if contested or changed by RFC
review_status: draft                # only a legal reviewer sets legal-reviewed
since: "2025.11-draft.1"
references:
  - title: DPDP Rules, 2025
    url: https://www.meity.gov.in/
```

## Guidelines

- **Atomic.** One requirement per control. If a question needs "and" to join two
  different obligations, consider two controls or two questions.
- **Cite precisely.** Use the narrowest Section, sub-section or Rule you can.
- **Keep facts and interpretation apart.** The description restates the law; the
  `interpretation.note` explains how the test approximates it and where it falls short.
- **Choose confidence honestly.**
  - `high`: the text is explicit and the test checks it directly.
  - `medium`: the test is a reasonable proxy for a broader requirement.
  - `contested`: credible readings differ. Summarise each reading and link the RFC.
- **Questions must be answerable with yes or no**, and "yes" must mean the
  requirement is met (set `expect: "no"` only if unavoidable).
- **Severity:** `critical` for harm to many Data Principals or core statutory
  duties (security, breach, children, tracking before consent), `high` for core
  notice, consent and rights duties, `medium` for supporting duties, `low` for
  good practice.

## Organisation-specific controls

Put them in your own directory with your own prefix (for example `ACME-POL-001`),
add the directory to your overlay's `extra_controls`, and include them by id or
tag. See [`examples/org-controls`](../examples/org-controls).
