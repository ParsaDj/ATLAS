# v0.1.0 release checklist

This checklist separates evidence required for the first public software release
from later hardware and hosted-model validation. Publishing v0.1.0 means the
documented synthetic workflow is reproducible; it does not claim physical robot
safety, production readiness, or live-model accuracy.

## Required before tagging

- [ ] Confirm `VERSION`, Python package metadata, dashboard package metadata,
  and the API `/version` response all report `0.1.0`.
- [ ] Confirm the Python, dashboard, browser, and Docker Compose workflows pass
  on the exact `main` commit to be tagged.
- [ ] Run the documented Compose failure demo from a clean clone and verify the
  incident cites its event, mission, and approved document revision.
- [ ] Inspect the generated browser recording, screenshot, incident report, and
  evidence summary from that commit.
- [ ] Confirm the prohibited-name scan and secret scan are clean.
- [ ] Review `CHANGELOG.md`, known limits, third-party attribution, and Apache
  2.0 license text.
- [ ] Create annotated tag `v0.1.0` on the verified commit and push the tag.
- [ ] Confirm the Release workflow publishes the source archive, manifest, and
  `SHA256SUMS`; download them and verify the checksums.

## Evidence to record

Record these values in the release notes so another developer can reproduce the
same result:

| Evidence | Value |
| --- | --- |
| Git commit | Exact 40-character SHA |
| Release tag | `v0.1.0` |
| Python | `3.13` |
| Node.js | `22` |
| PostgreSQL | `17` |
| Python tests | Passing count from CI |
| Browser workflows | Passing count from CI |
| Compose smoke run | Workflow link |
| Source checksum | Value from `SHA256SUMS` |

## Follow-up evidence

These strengthen the portfolio but do not block the synthetic software release:

- Ubuntu 24.04, ROS 2 Jazzy, Gazebo Harmonic, and Nav2 runtime acceptance.
- A named live-model benchmark with exact model and prompt versions.
- A narrated two-minute walkthrough made from the reproducible demo.
- Hardware validation on an appropriately licensed ROS 2 robot platform.

## Publication boundary

The release must continue to describe ATLAS as a simulated, single-facility
portfolio system. Do not claim that its synthetic measurements establish
physical robot safety, production fleet reliability, or general model accuracy.
