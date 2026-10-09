# Reproducible portfolio demo artifacts

The dashboard workflow captures ATLAS's main failure story with a real browser
and API. It creates and approves a Robot 3 inspection mission, injects a failed
sensor observation, opens the resulting incident, runs the evidence-grounded
investigation, and verifies the event and approved document citations.

## Capture locally

Install the dashboard dependencies and Chromium as described in the README,
then run:

```sh
cd apps/dashboard
pnpm demo:capture
```

The command starts an isolated temporary API and writes three files under
`apps/dashboard/demo-artifacts/`:

- `atlas-incident-investigation.png` shows the customer-facing investigation;
- `atlas-incident-report.html` is the downloadable incident report; and
- `atlas-demo-evidence.json` records the mission, injected event, incident,
  citations, confidence, limitation, and recommended next step.

Generated files are ignored by Git because mission and incident identifiers
change on each run. GitHub Actions uploads the same directory as the
`atlas-portfolio-demo` workflow artifact after the full browser suite passes.
This makes every revision's visual evidence independently downloadable without
committing generated screenshots or claiming that synthetic results came from
physical hardware.
