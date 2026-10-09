# Reliability invariants

ATLAS defines correctness as invariants that must hold across request retries,
out-of-order observations, conflicting identifiers, and competing state
transitions. These are exercised against SQLite locally and PostgreSQL in CI.

## Mission invariants

1. A mission begins in `pending` and requires a separate authenticated approval
   before reaching `running`.
2. A terminal mission (`completed`, `failed`, or `cancelled`) never returns to
   `running` and cannot change to another terminal state.
3. One robot has at most one running mission.
4. Managed execution advances exactly one step from committed progress and
   cannot skip a waypoint.
5. Cancellation racing telemetry cannot resurrect the mission or commit
   unvalidated movement.

## Evidence invariants

1. One event ID identifies exactly one canonical payload.
2. Retrying that payload succeeds as a duplicate without creating another row.
3. Reusing the ID with different content is a conflict.
4. A mission fault and its triggering event commit in the same transaction.
5. Repeated observations of one fault create at most one incident for that
   mission and fault type.
6. Historical telemetry remains queryable but cannot regress the live snapshot
   or create a historical incident.

## Authorization and audit invariants

1. Every human operational mutation requires a valid session, role, and CSRF
   secret.
2. Every successful human state transition creates an attributable audit entry
   in the same transaction.
3. Model output cannot invoke a state transition.
4. Robot credentials cannot approve missions or maintenance work.

## Generated state-machine traces

`tests/test_state_machine_properties.py` runs 50 reproducible traces using seed
`20261009`. Every trace creates and approves a mission, then generates twelve
operations selected from:

- fresh telemetry;
- stale telemetry;
- identical event replay; and
- event-ID substitution with altered content.

Each trace then selects completion, sensor failure, or cancellation and follows
the terminal transition with late telemetry, repeated approval, repeated
cancellation, and event replay. After every operation, the test checks the
modelled mission state. At the end it compares stored event IDs, incident count,
and audit actions with the expected model.

The seed makes a failing trace reproducible. This generated test broadens the
ordering coverage but is not a formal proof, a distributed failure test, or a
substitute for Gazebo and physical-robot validation.
