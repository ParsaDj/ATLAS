# ATLAS — Autonomous Task & Logistics Agent System

Independent robotics and AI portfolio project. Uses five simulated robots and entirely synthetic industrial data. No employer systems, proprietary models, real customer information, or physical robot commands are involved.

## Current implementation

ATLAS now includes a FastAPI service, persistent SQLAlchemy storage, five seeded robots, mission execution, searchable event history, telemetry validation, incident detection, and a deterministic fault demo. The React/TypeScript dashboard provides fleet monitoring, mission creation/approval/cancellation, waypoint progress, incident evidence, event history, and read-only incident investigation. ROS 2 integration, tickets, authentication, audit logging, and an optional hosted-model adapter remain future milestones.

## Run locally on macOS

Requires Python 3.11 or newer (tested with 3.13). From the repository directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

SQLite is the default and `alembic upgrade head` creates or upgrades `atlas.db`. The API seeds the five synthetic robots after the schema is current; it never creates or alters tables. No Docker, paid model, or robotics installation is needed. Use one API worker for this demo.

Open http://127.0.0.1:8000/docs for the interactive API. In a second terminal:

```sh
source .venv/bin/activate
python -m simulator.fleet
```

The simulator creates and approves one mission per robot, writes events to `events.jsonl`, and sends telemetry every five seconds for ten ticks (about 50 seconds). The file is append-only; each run has unique event identifiers.

Expected results on a fresh database:

| Robot | Outcome |
| --- | --- |
| Robot 1 | Mission completed |
| Robot 2 | Low battery incident; mission failed |
| Robot 3 | Sensor failure incident; mission failed |
| Robot 4 | Stops reporting; disconnection incident; mission failed |
| Robot 5 | Mission completed |

```sh
curl http://127.0.0.1:8000/api/robots
curl http://127.0.0.1:8000/api/incidents
curl http://127.0.0.1:8000/api/robots/robot-3/telemetry
```

Use a returned mission ID with `GET /api/missions/{mission_id}` to inspect the failed mission. Incidents cite the first triggering event ID; disconnection has no triggering event and records the detection time instead. Historical events remain accessible through robot telemetry.

Run `POST /api/incidents/{incident_id}/investigate` or select **Investigate incident** in the dashboard to produce an evidence-grounded explanation. The first implementation is deterministic and works without an API key or paid model. It reads only the incident's mission, referenced events, and approved local troubleshooting guides. Each result includes a confidence level, explicit limitations, a recommended next step, citations, and a read-only tool trace. It cannot create tickets, reschedule missions, or command robots.

A rerun creates new missions and retains previous records. After the simulator exits, the heartbeat monitor will eventually mark the remaining robots disconnected too. Inspect the printed incident list at the end of the demo for the three intended faults. An interrupted run can leave running missions. The simulator checks for these before creating any new missions. Find them with `GET /api/missions?status=running`, then cancel each using `POST /api/missions/{id}/cancel` with `{"reason":"Restart interrupted demo"}`. Cancellation is a terminal state and retains all evidence. You can then rerun the simulator. To start a separate dataset without removing data, first run `DATABASE_URL=sqlite:///./another-demo.db alembic upgrade head`, then start the API with the same `DATABASE_URL`.

List missions with `GET /api/missions?robot_id=robot-3&status=failed`, retrieve their telemetry with `GET /api/events?mission_id=YOUR_MISSION_ID`, and follow incident evidence with `GET /api/events/{event_id}`. Mission, event, incident, and robot telemetry lists accept `limit` (1–1000, default 100) and `offset` (default 0). Event and incident lists accept `robot_id` and `mission_id` filters.

## Operations dashboard

The dashboard uses the actual API and refreshes every five seconds. It includes fleet status and last-reported positions, mission proposals and approval, cancellation with a reason, incident details, and direct access to triggering event records. Northstar Industries is a fictional customer. The position view is a synthetic coordinate plot, not a surveyed facility map.

Requires Node.js 22.12+ and pnpm 11.25.0. Install pnpm using `npm install --global pnpm@11.25.0`, then from the repository root:

```sh
cd apps/dashboard
pnpm install --frozen-lockfile
pnpm build
cd ../..
.venv/bin/alembic upgrade head
.venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 to use the dashboard. The build must exist **before starting the API**, which serves the compiled dashboard from the same origin. API-only use remains supported when no build exists.

For frontend development, run the API on port 8000 and `pnpm dev` from `apps/dashboard` in a second terminal. Vite serves the dashboard on port 5173 and proxies `/api` requests to the backend. No CORS wildcard or frontend API key is required.

The dashboard displays up to ten missions or incidents per page and twenty recent events per detail view. Triggering evidence is retrieved separately by event ID, so older fault evidence remains accessible. Unavailable evidence is shown as unavailable. API failures preserve the last successful snapshot and show a stale-data warning. To execute dashboard-created missions, start the operations worker in another terminal:

```sh
.venv/bin/python -m simulator.worker
```

It waits for approvals, follows each waypoint in order (one simulation unit per tick, default two-second interval), persists progress, and sends idle heartbeats after completion or cancellation. The dashboard shows reached waypoints. This healthy operations mode reports a fixed synthetic 100% battery and no sensor fault; use the separate `simulator.fleet` scenario to demonstrate faults. **Do not run both producers against the same facility at once.**

The worker re-reads authoritative state each tick. Cancellation blocks in-flight execution updates at the server. A short restart resumes the last committed position and waypoint; repeated delivery and competing workers cannot advance the same execution step twice. If the worker stays offline beyond the 15-second heartbeat window and the watchdog fails the mission, restarting restores connectivity but does not resurrect the failed mission. Create and approve a new mission to retry. A long API outage can likewise require a new mission.

With Compose, run `docker compose --profile operations up --build` to start the database, API/dashboard, and worker together. The existing `demo` profile remains a separate fault demonstration.

## PostgreSQL with Docker Compose

Requires Docker with Compose. The credentials below are local demo credentials.

```sh
docker compose up --build -d db api
curl http://127.0.0.1:8000/health
# Once health returns {"status":"ok"}:
docker compose --profile demo run --rm simulator
```

The multi-stage Dockerfile builds the dashboard and serves it through the API on port 8000. The API binds to loopback. PostgreSQL persists in the `atlas-data` volume; `docker compose down` retains it. Simulator output inside its disposable container is ephemeral; use the local simulator against the Compose API to retain `events.jsonl` locally.

`DATABASE_URL` selects the database. `.env.example` documents its format; the Python service does not automatically load `.env`. The container runs `alembic upgrade head` before starting Uvicorn. Existing pre-Alembic ATLAS databases are adopted by the initial migration after their table shape is validated, preserving their records.

For local schema changes, update the SQLAlchemy models, generate a candidate revision with `alembic revision --autogenerate -m "description"`, review it, and run `alembic upgrade head`. Use `alembic current` to inspect the applied revision. Starting the API against an unmigrated database fails instead of silently changing its schema.

## Tests

```sh
.venv/bin/python -m pytest -q
```

Tests use isolated SQLite databases and a controllable clock, including a full five-robot scenario, concurrent duplicate delivery, concurrent mission approval, missing first heartbeat, recovery, validation, out-of-order events, invalid mission transitions, and incident investigation. A separate reproducible evaluation covers 120 synthetic incidents across low battery, sensor failure, and disconnection cases. GitHub Actions is configured to run the workflow suite against both SQLite and a PostgreSQL 17 service. For your own PostgreSQL test database, set `ATLAS_TEST_POSTGRES_URL` before invoking pytest; each test uses an isolated temporary schema and removes only that schema afterward. The test user needs schema creation permission.

Current verification totals are recorded in `docs/evaluation.md`. The backend GitHub Actions job runs against both SQLite and PostgreSQL 17, and the dashboard job builds the UI and runs browser workflows. Docker Compose itself remains unverified locally because Docker is unavailable.

Dashboard workflow tests use Chromium and a fresh temporary SQLite database on port 8011; they never touch `atlas.db`:

```sh
cd apps/dashboard
pnpm exec playwright install chromium
ATLAS_TEST_PYTHON=../../.venv/bin/python pnpm test:e2e
```

Build the dashboard first. The five tests cover incident evidence and linked missions, mission creation/approval/cancellation, API outage/recovery, mobile navigation, and a dashboard-approved mission completing through a real worker process. CI also runs these workflows against a real API (SQLite).

## Project map

- `apps/api/main.py`: API, persistence, mission transitions, heartbeat monitor.
- `migrations/`: versioned SQLite/PostgreSQL schema changes managed by Alembic.
- `apps/ai_agent/`: read-only evidence engine and approved troubleshooting guides.
- `apps/dashboard/`: React/TypeScript customer dashboard and browser tests.
- `simulator/fleet.py`: reproducible synthetic fleet and JSONL event output.
- `tests/test_api.py`: workflow and reliability tests.
- `tests/evaluations/`: reproducible synthetic incident evaluation dataset.
- `docs/architecture.md`: contracts, state handling, and design tradeoffs.
- `docs/requirements.md`: scope and next milestones.
- `docs/safety.md`: boundaries and approval model.
- `docs/evaluation.md`: tested behavior and limitations.

This is a local development prototype. A license and repository publication should be selected by the project owner before distributing it as open source.
