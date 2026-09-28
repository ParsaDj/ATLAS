# Architecture

```mermaid
flowchart LR
  Simulator[Five synthetic robots] -->|POST telemetry| API[FastAPI]
  API --> DB[(SQLite or PostgreSQL)]
  API --> Investigator[Read-only evidence engine]
  Investigator --> Guides[Approved troubleshooting guides]
  Monitor[Heartbeat monitor] --> DB
  Operator[React dashboard / interactive API docs] --> API
  Future[Future ROS 2 bridge] -. same telemetry contract .-> API
```

## Telemetry contract

Each event has a caller-generated unique `event_id`, registered `robot_id`, timezone-aware `occurred_at`, position, battery percentage, sensor status, and optional mission ID. The backend adds `received_at`. UTC-normalized event time determines whether a sample can update the robot snapshot. Identical retries return `duplicate: true`; reuse of an event ID with another payload returns 409. Duplicate retries do not update liveness.

Telemetry for an unapproved, nonexistent, or differently assigned mission is rejected. Late records are stored but do not regress the current snapshot or generate historical fault incidents. Samples more than 15 seconds old are historical-only, even if no previous sample exists; they cannot claim a live robot connection. Records for a prior mission cannot mutate current robot state. This prototype assumes an ordered live producer; historical incident reconstruction is deferred.

## State and transactions

Missions transition `pending → running → completed|failed`. Pending or running missions may also become `cancelled`, with a required nonblank reason. Cancellation keeps telemetry and never resurrects the mission. Approval starts the synthetic mission; there is no physical dispatch. Only one mission may be running for a robot. Failed, cancelled and completed missions stay terminal; recovered connectivity does not resurrect a mission. Create a new mission to retry.

Telemetry insertion, snapshot update, incident creation, and failure transition share one database transaction. A unique telemetry primary key and incident deduplication key protect retries. Per-mission fault keys collapse repeated samples for the same fault into one incident. For unassigned robots, fault incidents deduplicate by event ID only; fault episode grouping is deferred.

PostgreSQL uses robot row locks to serialize conflicting writes. SQLite uses `BEGIN IMMEDIATE` transactions because it lacks equivalent row locks. SQLite is intended for the small local demo, not high-throughput ingestion. Mission, robot, telemetry, and incident payloads currently use JSON columns; schema normalization, foreign keys, and indexes should precede larger datasets.

## Schema migrations

Alembic owns the database schema. The API startup path never calls `create_all`; after migrations are applied, it only inserts any missing synthetic robot seed records. The initial revision creates robots, missions, telemetry, and incidents plus Alembic's version table on both SQLite and PostgreSQL. It can adopt a pre-Alembic ATLAS database when the existing table columns match the expected legacy schema, without changing its operational data.

Local and CI tests migrate each isolated database before creating the application. The Docker image runs `alembic upgrade head` before Uvicorn, after Compose has confirmed PostgreSQL is healthy. Future model changes require a reviewed revision rather than implicit startup DDL.

## Fault rules

- Battery below 20%: low battery incident.
- Sensor status `failed`: sensor failure incident. If a sample also reports low battery, both faults create incidents in the same transaction.
- No fresh heartbeat for more than 15 seconds: disconnection incident, checked every five seconds.
- An approved mission with no first heartbeat also times out, using approval time as its initial reference. This applies even when the robot was already disconnected before approval.

The heartbeat monitor runs inside one API process. Do not use multiple workers for this prototype. Database exceptions are logged and retried at the next interval. A separate scheduled worker and explicit watchdog health should precede production deployment.

## API

`GET /health`; `GET /api/robots`; `GET /api/robots/{id}`; `GET /api/robots/{id}/telemetry?limit=100`; `GET /api/missions`; `POST /api/missions`; `GET /api/missions/{id}`; `POST /api/missions/{id}/approve`; `POST /api/missions/{id}/cancel`; `GET /api/events`; `GET /api/events/{event_id}`; `POST /api/telemetry`; `GET /api/incidents`; `GET /api/incidents/{id}`; `POST /api/incidents/{id}/investigate`.

OpenAPI schemas and request examples are available at `/docs`. Ticket creation remains deferred until authenticated server-side approval exists.

## Incident investigation

The API loads one incident, its linked mission, and the exact event identifiers recorded by that incident, then passes those authorized records to `apps/ai_agent`. The evidence engine has no database session and exposes no write tools. It matches recognized fault types to approved local guides and returns a finding, calibrated confidence, limitations, next step, citations, and tool trace. Missing referenced evidence forces an insufficient result. Heartbeat-loss investigations remain limited because watchdog incidents have no triggering telemetry event.

This deterministic renderer is the first agent contract and requires no paid model. A later LLM adapter may render the same evidence package, but the API remains responsible for record access and any future authorization. Documents are bundled with the service and identified by stable IDs so evaluation can verify citations.

List endpoints for missions, events, incidents and robot telemetry support bounded limit/offset pagination with deterministic ordering. Event and incident lists filter by robot or mission; mission lists filter by robot and state. Offset pagination is a local-demo convenience; concurrently arriving data can shift page boundaries. Cursor pagination and indexed normalized columns remain future work.

## Customer dashboard

React/TypeScript lives in `apps/dashboard`. Vite builds static assets; FastAPI mounts them at `/` when the build directory exists, after registering API routes. The Dockerfile builds the frontend in a Node stage and copies only its compiled assets into the Python runtime. During development Vite proxies API requests to port 8000.

The UI polls every five seconds with non-overlapping requests per resource and aborts requests when a view changes. Failed refreshes retain the last successful data and explicitly mark it stale. Native modal dialogs keep keyboard focus inside the selected workflow. Creating a mission saves a pending proposal; a separate approval action begins execution. Mutations are disabled while pending and the backend validates all state transitions.

Incident details retrieve referenced evidence separately from the paginated event timeline. Missing evidence is an error state, never replaced with an AI explanation. The coordinate plot uses last reported positions; it is not a navigation map.

## Resumable synthetic execution

`python -m simulator.worker` polls the five registered robots and their linked missions. Only running (approved) missions move. Each execution event carries a deterministic mission/step event ID, the next execution step, and completed-waypoint count. The API holds the robot row lock, refreshes mission state, and validates the next step, motion toward the next waypoint, reached count, freshness, and final completion before committing telemetry and progress together. A step cannot skip waypoints or exceed one simulation unit. Legacy fault-demo telemetry remains supported separately.

Progress lives in mission JSON (`execution_step`, `completed_waypoints`, `execution_position`) and defaults safely for older records. No new SQL columns are required. Cancellation racing an uncommitted execution event returns 409, while an already committed event retry returns its original duplicate result. The worker re-reads progress after a 409 or restart. Only run one producer mode per facility. This is a local synthetic integration contract, not authentication or a robot safety controller.

The worker sends unassigned idle heartbeats when no running mission exists. Those can update liveness after a terminal mission but cannot modify its outcome. Battery remains fixed at 100% in this healthy operations mode. Recorded fault scenarios remain in the separate fleet demo.
