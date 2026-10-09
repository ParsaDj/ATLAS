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

The command starts an isolated temporary API and writes four files under
`apps/dashboard/demo-artifacts/`:

- `atlas-incident-investigation.webm` records the sign-in, incident selection,
  evidence-grounded investigation, citations, and uncertainty boundary;
- `atlas-incident-investigation.png` shows the customer-facing investigation;
- `atlas-incident-report.html` is the downloadable incident report; and
- `atlas-demo-evidence.json` records the mission, injected event, incident,
  citations, confidence, limitation, recommended next step, and exact ATLAS
  build provenance.

The recording is intentionally short and silent so it can be reviewed quickly
and remains suitable for captions or narration in a final portfolio edit.
Generated files are ignored by Git because mission and incident identifiers
change on each run. GitHub Actions uploads the same directory as the
`atlas-portfolio-demo` workflow artifact after the full browser suite passes.
This makes every revision's visual evidence independently downloadable without
committing generated screenshots or claiming that synthetic results came from
physical hardware.

## Refresh the README preview

The README uses a compact GIF derived from the browser recording. After a
successful capture, regenerate it with:

```sh
./scripts/build_demo_preview.sh
```

The browser recording uses a 1920×1080 viewport and output size. The README
conversion uses eight frames per second, a 960-pixel width, and a full 256-color
adaptive palette. Review the result before committing it; the CI WebM remains
the higher-quality evidence artifact.
