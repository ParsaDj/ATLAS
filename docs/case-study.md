# ATLAS engineering case study

## The operational problem

Small robotics teams often investigate a failed mission by manually joining
robot telemetry, mission state, fault events, technical guidance, and earlier
maintenance work. The records may arrive late or more than once, and an error
message rarely proves a physical root cause by itself.

ATLAS is a synthetic, single-facility prototype that demonstrates a safer
workflow: preserve the operational evidence, reconstruct what happened, state
what the evidence cannot establish, and require a human for every write that
follows the investigation.

## The demonstrated workflow

1. An operator creates and separately approves an inspection mission.
2. A simulator or authenticated ROS 2 bridge reports telemetry with a stable
   event identifier.
3. The API commits the event, robot snapshot, mission transition, incident, and
   audit evidence within explicit transaction boundaries.
4. The investigator receives only the linked mission, cited events, and latest
   approved document revisions.
5. It returns a finding, limitations, next step, citations, and tool trace.
6. An operator may separately propose or approve maintenance or a replacement
   mission. The investigator has no write or robot-control tool.

The portfolio demonstration injects one failed sensor observation for Robot 3.
ATLAS fails the mission, creates one incident, and supports a sensor-path
failure using the exact mission, event, and approved guide. It does not claim
that the evidence distinguishes hardware failure, obstruction, calibration
drift, or transient communication loss.

## Engineering decisions

| Decision | Reason | Evidence |
| --- | --- | --- |
| Stable caller-generated event IDs | Network retries must not create duplicate operational facts | Concurrent duplicate-delivery tests store one event and one incident |
| State and evidence in one transaction | A visible failure must retain the record that caused it | Telemetry, robot state, mission failure, incidents, and audit effects commit together |
| Durable bridge outbox | Robot observations must survive interrupted API connectivity | Restart and replay tests retain events and preserve idempotency |
| Read-only investigation boundary | Explanations must not become robot commands or maintenance authorization | The investigator receives an evidence envelope and exposes no write tools |
| Immutable approved documents | A finding must be traceable to the guidance used at that time | Citations include document ID, version, and SHA-256 content hash |
| Deterministic baseline with optional model adapter | The core demo must remain free, reproducible, and measurable | Provider failures and invalid model output fall back to the tested baseline |
| Explicit production guards | Demo credentials and SQLite must not be mistaken for deployment defaults | Production mode requires PostgreSQL, HTTPS, secure cookies, and strong secrets |

## Measured evidence

- 257 Python tests cover API behavior, transactions, concurrency, security,
  migrations, the ROS-independent bridge, investigation contracts, and
  evaluation scenarios.
- 120 deterministic incident cases verify tool selection, required citations,
  expected confidence, and explicit limitations in the synthetic dataset.
- 50 generated mission/event traces exercise retries, stale events, invalid
  transitions, cancellation, completion, and fault combinations.
- 11 Playwright workflows run against the real API; a separate browser capture
  records the Robot 3 failure story and exports its evidence.
- PostgreSQL 17 and SQLite run the shared workflow tests.
- Docker Compose CI builds the real image, applies migrations, runs the failure
  workflow, restarts the database and API, verifies persisted recovery, and
  executes a telemetry benchmark smoke workload.

These results describe the versioned synthetic environment. They do not
measure physical safety, production fleet availability, or general-purpose
model accuracy.

## What the model adds

ATLAS first builds the authorized evidence envelope on the server. The optional
model adapter can render that evidence into a more flexible explanation, but it
cannot retrieve arbitrary records or perform writes. Its response must match a
closed schema and cite only evidence supplied in the envelope. Fabricated or
missing citations, malformed output, prohibited claims, timeouts, and provider
errors return the deterministic result. A frozen 12-case runner records the
model, prompt, dataset, and evidence digests; no live-model score is published
until that runner is executed against a named model version.

## Current boundary

The ROS-independent transport, durable outbox, mission reconciliation, and
`rclpy`/Nav2 adapter are implemented and tested without ROS. Runtime acceptance
with Ubuntu 24.04, ROS 2 Jazzy, Gazebo Harmonic, and Nav2 remains outstanding.
ATLAS does not publish raw motor commands and is not a physical safety
controller. The prototype uses one API worker, local identity, process-local
login limiting and heartbeat monitoring, and a synthetic coordinate view.

## Reproduce the evidence

- [Run the two-minute failure demonstration](demo.md)
- [Inspect the evaluation procedure and limits](evaluation.md)
- [Review reliability invariants](reliability.md)
- [Review the security threat model](security/threat-model.md)
- [Follow the ROS 2 runtime acceptance plan](ros2-integration.md)
