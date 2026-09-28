# Evaluation

Run `python -m pytest -q`. Current tests verify synthetic operational behavior, not AI accuracy or physical safety.

The full-fleet test advances a controlled clock through the simulator scenario and asserts two completed missions, three failed missions, and the three expected incident types. Other tests check duplicate delivery (including concurrent retries), conflicting event IDs, concurrent approvals, invalid state transitions, input validation, stale telemetry, missing heartbeats, and recovery without resurrecting failed missions.

SQLite is verified locally, and the initial GitHub Actions run passed the workflow suite against PostgreSQL 17. The shared fixture can run the workflow tests against PostgreSQL in isolated schemas using ATLAS_TEST_POSTGRES_URL. CI now provisions PostgreSQL 17 for this. Docker Compose still needs an integration run; the GitHub PostgreSQL service verifies database behavior but does not build the application container.

Future AI evaluations must record model version, prompt version, dataset version, tool selection, citation support, and uncertainty behavior. Keep expected answers separate from agent-visible inputs. The blueprint's 95% targets and 100 incident scenarios are targets, not achieved measurements.

## Initial local verification

Python 3.13: 38 tests passed. A live 50-second HTTP demo produced the three expected incidents, with two completed and three failed missions. Dependency tooling emits a Starlette/httpx deprecation warning; all assertions pass. PostgreSQL was verified through the initial GitHub Actions run.

## Reliability review

Regression tests first reproduced three failures: an already-disconnected robot's new mission never timing out, simultaneous sensor and battery faults losing one incident, and an hour-old first heartbeat claiming the robot was online. All three now pass. Additional coverage checks cancellation, terminal-state preservation, history filtering/pagination, evidence retrieval, stable retry payloads, and simulator preflight behavior.

## Dashboard milestone

The production TypeScript/Vite build succeeds. Five Playwright tests pass against the real API with a temporary SQLite database: failure evidence and mission linkage; mission proposal, approval, and cancellation; stale-data warnings and retry recovery during a simulated API outage; and mobile navigation without horizontal page overflow. Browser data is synthetic. The suite does not measure AI accuracy or authorize physical robot actions.

A backend regression test additionally rejects telemetry for a mission cancelled before it was ever approved. This closes an approval bypass caused by checking only the current mission state.

## Mission execution validation

Seven additional API/worker tests cover ordered completion, restarting from committed progress, cancellation between read and delivery, concurrent/lost-ack duplicate delivery, rejected skipped-waypoint motion, pending and timed-out missions, and repeated/negative-coordinate waypoints. These run on SQLite locally and PostgreSQL in CI. A fifth browser test launches a real worker process and confirms a dashboard-created/approved mission reaches all waypoints. Local totals: 38 Python tests and five browser tests pass.
