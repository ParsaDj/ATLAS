# Evaluation

Run `python -m pytest -q`. Current tests verify synthetic operational behavior and deterministic evidence handling, not physical safety or open-ended model accuracy.

The full-fleet test advances a controlled clock through the simulator scenario and asserts two completed missions, three failed missions, and the three expected incident types. Other tests check duplicate delivery (including concurrent retries), conflicting event IDs, concurrent approvals, invalid state transitions, input validation, stale telemetry, missing heartbeats, and recovery without resurrecting failed missions.

SQLite is verified locally, and the initial GitHub Actions run passed the workflow suite against PostgreSQL 17. The shared fixture can run the workflow tests against PostgreSQL in isolated schemas using ATLAS_TEST_POSTGRES_URL. CI now provisions PostgreSQL 17 for this. Docker Compose still needs an integration run; the GitHub PostgreSQL service verifies database behavior but does not build the application container.

## Incident investigation evaluation

`tests/evaluations/test_incident_dataset.py` generates 120 reproducible scenarios across low battery, sensor failure, and disconnection faults. Expected confidence and document IDs live in the test assertions, outside the records passed to the investigator. The suite requires the correct approved guide, mission citation, allowed read-only tool set, and an explicit limitation for every case. Additional API tests cover missing incidents, absent referenced events, unknown fault types, citation content, and conservative uncertainty.

All 120 controlled cases pass the current contract, so tool selection and required evidence citation are 100% for this synthetic dataset. This is a deterministic baseline rather than a measurement of a general-purpose LLM. Dataset versioning and model/prompt versioning will be added if a hosted model adapter is introduced.

## Initial local verification

Python 3.13: 203 tests pass locally, including 120 investigation evaluation cases, four migration checks, versioned document retrieval and approval, authentication/authorization, maintenance-ticket, escaped report and replacement-mission coverage, bridge authentication, durable outbox and Nav2 mission-reconciliation behavior, and simulator login handling. A live 50-second HTTP demo produced the three expected incidents, with two completed and three failed missions. Dependency tooling emits a Starlette/httpx deprecation warning; all assertions pass. PostgreSQL verification runs in GitHub Actions.

## Reliability review

Regression tests first reproduced three failures: an already-disconnected robot's new mission never timing out, simultaneous sensor and battery faults losing one incident, and an hour-old first heartbeat claiming the robot was online. All three now pass. Additional coverage checks cancellation, terminal-state preservation, history filtering/pagination, evidence retrieval, stable retry payloads, and simulator preflight behavior.

## Dashboard milestone

The production TypeScript/Vite build succeeds. Five Playwright tests run against the real API with a temporary SQLite database: failure evidence, linked missions, and investigation citations; mission proposal, approval, and cancellation; stale-data warnings and retry recovery during a simulated API outage; mobile navigation without horizontal page overflow; and real worker mission completion. Browser data is synthetic. The suite does not authorize physical robot actions.

A backend regression test additionally rejects telemetry for a mission cancelled before it was ever approved. This closes an approval bypass caused by checking only the current mission state.

## Mission execution validation

Seven additional API/worker tests cover ordered completion, restarting from committed progress, cancellation between read and delivery, concurrent/lost-ack duplicate delivery, rejected skipped-waypoint motion, pending and timed-out missions, and repeated/negative-coordinate waypoints. These run on SQLite locally and PostgreSQL in CI. A fifth browser test launches a real worker process and confirms a dashboard-created/approved mission reaches all waypoints.

## Migration validation

Four tests verify fresh schema creation, metadata drift detection, downgrade/reapply behavior, rejection of an unmigrated database, and adoption of a legacy schema without losing records. The dashboard integration server also migrates its temporary SQLite database before startup. GitHub Actions runs a standalone migration smoke test and exercises the application suite against PostgreSQL 17.

## Authentication validation

Tests cover missing authentication, missing CSRF protection, administrator user creation without credential disclosure, technician mission-write denial, authenticated incident investigation, audit attribution, eight-hour session expiry, and simulator login. Six browser workflows include administrator user creation, audit-history display, and sign-out. Authentication is local-only and does not claim readiness for an internet-facing deployment.
