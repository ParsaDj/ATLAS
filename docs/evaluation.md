# Evaluation

Run `python -m pytest -q`. Current tests verify synthetic operational behavior, not AI accuracy or physical safety.

The full-fleet test advances a controlled clock through the simulator scenario and asserts two completed missions, three failed missions, and the three expected incident types. Other tests check duplicate delivery (including concurrent retries), conflicting event IDs, concurrent approvals, invalid state transitions, input validation, stale telemetry, missing heartbeats, and recovery without resurrecting failed missions.

SQLite is verified locally. The shared fixture can run the workflow tests against PostgreSQL in isolated schemas using ATLAS_TEST_POSTGRES_URL. CI now provisions PostgreSQL 17 for this. PostgreSQL and Docker Compose still need an actual integration run before claiming backend parity. GitHub Actions is configured but has not run remotely until the repository is published.

Future AI evaluations must record model version, prompt version, dataset version, tool selection, citation support, and uncertainty behavior. Keep expected answers separate from agent-visible inputs. The blueprint's 95% targets and 100 incident scenarios are targets, not achieved measurements.

## Initial local verification

Python 3.13: 30 tests passed. A live 50-second HTTP demo produced the three expected incidents, with two completed and three failed missions. Dependency tooling emits a Starlette/httpx deprecation warning; all assertions pass. PostgreSQL remains unverified locally.

## Reliability review

Regression tests first reproduced three failures: an already-disconnected robot's new mission never timing out, simultaneous sensor and battery faults losing one incident, and an hour-old first heartbeat claiming the robot was online. All three now pass. Additional coverage checks cancellation, terminal-state preservation, history filtering/pagination, evidence retrieval, stable retry payloads, and simulator preflight behavior.
