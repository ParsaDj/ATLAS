# ATLAS — Autonomous Task & Logistics Agent System

Independent robotics and AI portfolio project. Uses five simulated robots and entirely synthetic industrial data. No employer systems, proprietary models, real customer information, or physical robot commands are involved.

## Current implementation

The first backend/simulator milestone includes a FastAPI service, persistent SQLAlchemy storage, five seeded robots, mission creation, approval and cancellation, searchable event history, telemetry validation, incident detection, and a deterministic fault demo. The React/TypeScript dashboard now provides fleet monitoring, mission creation/approval/cancellation, incident evidence, and event history. AI investigation, ROS 2 integration, tickets, authentication, and audit logging remain future milestones.

## Run locally on macOS

Requires Python 3.11 or newer (tested with 3.13). From the repository directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

SQLite is the default and creates `atlas.db` on startup. No Docker, paid model, or robotics installation is needed. Use one API worker for this demo.

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

A rerun creates new missions and retains previous records. After the simulator exits, the heartbeat monitor will eventually mark the remaining robots disconnected too. Inspect the printed incident list at the end of the demo for the three intended faults. An interrupted run can leave running missions. The simulator checks for these before creating any new missions. Find them with `GET /api/missions?status=running`, then cancel each using `POST /api/missions/{id}/cancel` with `{"reason":"Restart interrupted demo"}`. Cancellation is a terminal state and retains all evidence. You can then rerun the simulator. To start a separate dataset without removing data, use `DATABASE_URL=sqlite:///./another-demo.db uvicorn apps.api.main:app`.

List missions with `GET /api/missions?robot_id=robot-3&status=failed`, retrieve their telemetry with `GET /api/events?mission_id=YOUR_MISSION_ID`, and follow incident evidence with `GET /api/events/{event_id}`. Mission, event, incident, and robot telemetry lists accept `limit` (1–1000, default 100) and `offset` (default 0). Event and incident lists accept `robot_id` and `mission_id` filters.

## Operations dashboard

The dashboard uses the actual API and refreshes every five seconds. It includes fleet status and last-reported positions, mission proposals and approval, cancellation with a reason, incident details, and direct access to triggering event records. Northstar Industries is a fictional customer. The position view is a synthetic coordinate plot, not a surveyed facility map.

Requires Node.js 22.12+ and pnpm 11.25.0. Install pnpm using `npm install --global pnpm@11.25.0`, then from the repository root:

```sh
cd apps/dashboard
pnpm install --frozen-lockfile
pnpm build
cd ../..
.venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 to use the dashboard. The build must exist **before starting the API**, which serves the compiled dashboard from the same origin. API-only use remains supported when no build exists.

For frontend development, run the API on port 8000 and `pnpm dev` from `apps/dashboard` in a second terminal. Vite serves the dashboard on port 5173 and proxies `/api` requests to the backend. No CORS wildcard or frontend API key is required.

The dashboard displays up to ten missions or incidents per page and twenty recent events per detail view. Triggering evidence is retrieved separately by event ID, so older fault evidence remains accessible. Unavailable evidence is shown as unavailable. API failures preserve the last successful snapshot and show a stale-data warning. Mission approval only starts the backend workflow; the current synthetic simulator does not automatically execute arbitrary dashboard-created missions.

## PostgreSQL with Docker Compose

Requires Docker with Compose. The credentials below are local demo credentials.

```sh
docker compose up --build -d db api
curl http://127.0.0.1:8000/health
# Once health returns {"status":"ok"}:
docker compose --profile demo run --rm simulator
```

The multi-stage Dockerfile builds the dashboard and serves it through the API on port 8000. The API binds to loopback. PostgreSQL persists in the `atlas-data` volume; `docker compose down` retains it. Simulator output inside its disposable container is ephemeral; use the local simulator against the Compose API to retain `events.jsonl` locally.

`DATABASE_URL` selects the database. `.env.example` documents its format; the Python service does not automatically load `.env`. Database tables are created on first startup. Schema migrations are not implemented yet.

## Tests

```sh
.venv/bin/python -m pytest -q
```

Tests use isolated SQLite databases and a controllable clock, including a full five-robot scenario, concurrent duplicate delivery, concurrent mission approval, missing first heartbeat, recovery, validation, out-of-order events, and invalid mission transitions. GitHub Actions is configured to run the workflow suite against both SQLite and a PostgreSQL 17 service. For your own PostgreSQL test database, set `ATLAS_TEST_POSTGRES_URL` before invoking pytest; each test uses an isolated temporary schema and removes only that schema afterward. The test user needs schema creation permission.

Local verification: 31 Python tests pass. The initial backend GitHub Actions run passed against both SQLite and PostgreSQL 17. The updated dashboard CI job builds the UI and runs browser tests. Docker Compose itself remains unverified locally because Docker is unavailable.

Dashboard workflow tests use Chromium and a fresh temporary SQLite database on port 8011; they never touch `atlas.db`:

```sh
cd apps/dashboard
pnpm exec playwright install chromium
ATLAS_TEST_PYTHON=../../.venv/bin/python pnpm test:e2e
```

Build the dashboard first. The four tests cover incident evidence and linked missions, mission creation/approval/cancellation, API outage/recovery, and mobile navigation. CI also runs these workflows against a real API (SQLite).

## Project map

- `apps/api/main.py`: API, persistence, mission transitions, heartbeat monitor.
- `apps/dashboard/`: React/TypeScript customer dashboard and browser tests.
- `simulator/fleet.py`: reproducible synthetic fleet and JSONL event output.
- `tests/test_api.py`: workflow and reliability tests.
- `docs/architecture.md`: contracts, state handling, and design tradeoffs.
- `docs/requirements.md`: scope and next milestones.
- `docs/safety.md`: boundaries and approval model.
- `docs/evaluation.md`: tested behavior and limitations.

This is a local development prototype. A license and repository publication should be selected by the project owner before distributing it as open source.
