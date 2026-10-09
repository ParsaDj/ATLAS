# Evaluation

Run `python -m pytest -q`. Current tests verify synthetic operational behavior and deterministic evidence handling, not physical safety or open-ended model accuracy.

The full-fleet test advances a controlled clock through the simulator scenario and asserts two completed missions, three failed missions, and the three expected incident types. Other tests check duplicate delivery (including concurrent retries), conflicting event IDs, concurrent approvals, invalid state transitions, input validation, stale telemetry, missing heartbeats, and recovery without resurrecting failed missions.

SQLite is verified locally, and the initial GitHub Actions run passed the workflow suite against PostgreSQL 17. The shared fixture can run the workflow tests against PostgreSQL in isolated schemas using ATLAS_TEST_POSTGRES_URL. CI now provisions PostgreSQL 17 for this. Docker Compose still needs an integration run; the GitHub PostgreSQL service verifies database behavior but does not build the application container.

## Incident investigation evaluation

`tests/evaluations/test_incident_dataset.py` generates 120 reproducible scenarios across low battery, sensor failure, and disconnection faults. Expected confidence and document IDs live in the test assertions, outside the records passed to the investigator. The suite requires the correct approved guide, mission citation, allowed read-only tool set, and an explicit limitation for every case. Additional API tests cover missing incidents, absent referenced events, unknown fault types, citation content, and conservative uncertainty.

All 120 controlled cases pass the current contract, so tool selection and required evidence citation are 100% for this synthetic dataset. This is a deterministic baseline rather than a measurement of a general-purpose LLM.

The optional model adapter records the model name, prompt version, and SHA-256
digest of its exact evidence envelope. Contract tests reject extra response
fields, fabricated citations, omitted operational evidence, hypotheses that
reference unauthorized records, and instructions embedded in technical
documents. Provider and validation failures use the deterministic result.

These are boundary and adversarial tests, not a measurement of live-model
diagnostic accuracy. A named model, frozen evaluation dataset, repeated runs,
and published citation and unsupported-claim measurements are still required
before making an accuracy claim.

## Initial local verification

Python 3.13: 222 tests pass locally, including 120 investigation evaluation cases, seven optional-model contract and adversarial checks, six threat-model adversarial checks, five migration checks, observability and credential-redaction checks, login throttling and browser security headers, versioned document retrieval and approval, authentication/authorization, maintenance-ticket, escaped report and replacement-mission coverage, bridge authentication, durable outbox and Nav2 mission-reconciliation behavior, and simulator login handling. A live 50-second HTTP demo produced the three expected incidents, with two completed and three failed missions. Dependency tooling emits a Starlette/httpx deprecation warning; all assertions pass. PostgreSQL verification runs in GitHub Actions.

## Reliability review

Regression tests first reproduced three failures: an already-disconnected robot's new mission never timing out, simultaneous sensor and battery faults losing one incident, and an hour-old first heartbeat claiming the robot was online. All three now pass. Additional coverage checks cancellation, terminal-state preservation, history filtering/pagination, evidence retrieval, stable retry payloads, and simulator preflight behavior.

## Dashboard milestone

The production TypeScript/Vite build succeeds. Ten Playwright tests run against the real API with a temporary SQLite database. They cover failure evidence and versioned investigation citations; mission proposal, approval, and cancellation; document drafting and separate approval; stale-data warnings and retry recovery; mobile navigation; user and audit administration; maintenance completion; report downloads; replacement missions; and real worker mission completion. Browser data is synthetic. The suite does not authorize physical robot actions.

A backend regression test additionally rejects telemetry for a mission cancelled before it was ever approved. This closes an approval bypass caused by checking only the current mission state.

## Mission execution validation

Seven additional API/worker tests cover ordered completion, restarting from committed progress, cancellation between read and delivery, concurrent/lost-ack duplicate delivery, rejected skipped-waypoint motion, pending and timed-out missions, and repeated/negative-coordinate waypoints. These run on SQLite locally and PostgreSQL in CI. A fifth browser test launches a real worker process and confirms a dashboard-created/approved mission reaches all waypoints.

## Migration validation

Five tests verify fresh schema creation, metadata drift detection, downgrade/reapply behavior, rejection of an unmigrated database, adoption of a legacy schema without losing records, and indexed operational-record backfill. The dashboard integration server also migrates its temporary SQLite database before startup. GitHub Actions runs a standalone migration smoke test and exercises the application suite against PostgreSQL 17.

## Observability validation

Tests verify separate liveness and database-readiness responses, accepted and replaced correlation IDs, structured completion fields, 32-character trace IDs, credential omission, Prometheus content, operational state gauges, and route-template labels that do not include concrete resource IDs. The complete ten-workflow browser suite also passes against the instrumented API.

## Authentication validation

Tests cover missing authentication, missing CSRF protection, administrator user creation without credential disclosure, technician mission-write denial, authenticated incident investigation, audit attribution, eight-hour session expiry, and simulator login. The browser suite includes administrator user creation, audit-history display, and sign-out. Authentication is local-only and does not claim readiness for an internet-facing deployment.

Five failed logins from one client trigger a five-minute limit with a `Retry-After`
response; the test advances an injected clock and verifies successful recovery.
Security-header coverage includes error responses and HTTPS-only HSTS behavior.
