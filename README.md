# ATLAS — Autonomous Task & Logistics Agent System

Independent robotics and AI portfolio project. Uses five simulated robots and entirely synthetic industrial data. No employer systems, proprietary models, real customer information, or physical robot commands are involved.

## Current implementation

ATLAS now includes a FastAPI service, persistent SQLAlchemy storage, five seeded robots, mission execution, searchable event history, telemetry validation, incident detection, local role-based authentication, audit logging, and a deterministic fault demo. The React/TypeScript dashboard provides fleet monitoring, mission workflows, waypoint progress, incident evidence, investigation, user administration, audit history, human-approved maintenance tickets, and downloadable customer reports. The robotics integration includes machine authentication, mission polling, stable ROS event IDs, durable offline telemetry buffering, and a ROS 2 node that translates approved missions into Nav2 waypoint actions. Gazebo environment validation, approved mission rescheduling, and an optional hosted-model adapter remain future milestones.

## Run locally on macOS

Requires Python 3.11 or newer (tested with 3.13). From the repository directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
export ATLAS_BOOTSTRAP_ADMIN_PASSWORD='choose-at-least-12-characters'
export ATLAS_TELEMETRY_API_KEY='choose-a-long-random-bridge-key'
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

SQLite is the default and `alembic upgrade head` creates or upgrades `atlas.db`. On the first authenticated startup, `ATLAS_BOOTSTRAP_ADMIN_PASSWORD` creates the local `atlas-admin` account; later startups keep the stored account and do not reuse the environment value. The API seeds the five synthetic robots after the schema is current; it never creates or alters tables. No Docker, paid model, or robotics installation is needed. Use one API worker for this demo.

Open http://127.0.0.1:8000/docs for the interactive API. In a second terminal:

```sh
source .venv/bin/activate
export ATLAS_OPERATOR_PASSWORD='choose-at-least-12-characters'
export ATLAS_TELEMETRY_API_KEY='choose-a-long-random-bridge-key'
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

Operators and administrators can draft a maintenance ticket from an open incident and assign it to an active technician account. Approval is a separate action. Only the assigned technician or an administrator can start and resolve the approved work. Resolving the ticket atomically resolves the incident and records the resolution. Ticket creation, approval, start, and resolution are attributed in the audit log.

Authenticated users can download printable HTML reports from incident and mission details. Incident reports separate recorded facts from evidence-based findings, confidence, limitations, citations, and maintenance history. Mission reports include route, telemetry summary, incidents, and linked tickets. Customer-entered content is HTML-escaped, every generation is audited, and each report states that it contains synthetic records rather than physical-safety evidence.

A rerun creates new missions and retains previous records. After the simulator exits, the heartbeat monitor will eventually mark the remaining robots disconnected too. Inspect the printed incident list at the end of the demo for the three intended faults. An interrupted run can leave running missions. The simulator checks for these before creating any new missions. Find them with `GET /api/missions?status=running`, then cancel each using `POST /api/missions/{id}/cancel` with `{"reason":"Restart interrupted demo"}`. Cancellation is a terminal state and retains all evidence. You can then rerun the simulator. To start a separate dataset without removing data, first run `DATABASE_URL=sqlite:///./another-demo.db alembic upgrade head`, then start the API with the same `DATABASE_URL`.

List missions with `GET /api/missions?robot_id=robot-3&status=failed`, retrieve their telemetry with `GET /api/events?mission_id=YOUR_MISSION_ID`, and follow incident evidence with `GET /api/events/{event_id}`. Mission, event, incident, and robot telemetry lists accept `limit` (1–1000, default 100) and `offset` (default 0). Event and incident lists accept `robot_id` and `mission_id` filters.

## Operations dashboard

The dashboard uses the actual API and refreshes every five seconds. Sign-in uses an HttpOnly server-side session and a per-session CSRF token. Administrators manage local operator, technician, and administrator accounts and can review the audit history. Operators and administrators create, approve, and cancel missions; all authenticated roles can investigate incidents. Northstar Industries is a fictional customer. The position view is a synthetic coordinate plot, not a surveyed facility map.

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
ATLAS_TELEMETRY_API_KEY='choose-a-long-random-bridge-key' .venv/bin/python -m simulator.worker
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

Tests use isolated SQLite databases and a controllable clock, including a full five-robot scenario, concurrent duplicate delivery, concurrent mission approval, missing first heartbeat, recovery, validation, out-of-order events, invalid mission transitions, incident investigation, and maintenance authorization. A separate reproducible evaluation covers 120 synthetic incidents across low battery, sensor failure, and disconnection cases. GitHub Actions is configured to run the workflow suite against both SQLite and a PostgreSQL 17 service. For your own PostgreSQL test database, set `ATLAS_TEST_POSTGRES_URL` before invoking pytest; each test uses an isolated temporary schema and removes only that schema afterward. The test user needs schema creation permission.

Current verification totals are recorded in `docs/evaluation.md`. The backend GitHub Actions job runs against both SQLite and PostgreSQL 17, and the dashboard job builds the UI and runs browser workflows. Docker Compose itself remains unverified locally because Docker is unavailable.

## Robotics bridge preparation

`robotics/atlas_bridge` is the ROS-independent portion of the integration. It polls the approved mission for one robot, authenticates telemetry with `X-ATLAS-Bridge-Key`, assigns replay-safe IDs from the ROS timestamp and sequence, and writes every observation to a SQLite outbox before delivery. Temporary network, authentication, throttling, and server failures retain events for a later flush. Permanent validation failures move to a rejected-event table so a poisoned record cannot block newer observations.

This core and its mission state machine run and are tested on macOS. `robotics/atlas_ros` provides the `rclpy` wrapper that subscribes to odometry, battery, and diagnostics topics and sends approved waypoints to Nav2. Its Python syntax and package contract are checked locally; runtime validation still requires Ubuntu with ROS 2, Gazebo, and Nav2. See `docs/ros2-integration.md` for setup and acceptance steps.

Dashboard workflow tests use Chromium and a fresh temporary SQLite database on port 8011; they never touch `atlas.db`:

```sh
cd apps/dashboard
pnpm exec playwright install chromium
ATLAS_TEST_PYTHON=../../.venv/bin/python pnpm test:e2e
```

Build the dashboard first. The eight tests cover authentication, incident evidence, mission creation/approval/cancellation, audit administration, the complete maintenance workflow, downloaded customer reports, API outage/recovery, mobile navigation, and a dashboard-approved mission completing through a real worker process. CI also runs these workflows against a real API (SQLite).

## Project map

- `apps/api/main.py`: API, persistence, mission transitions, heartbeat monitor.
- `apps/api/reports.py`: escaped printable incident and mission report rendering.
- `migrations/`: versioned SQLite/PostgreSQL schema changes managed by Alembic.
- `apps/ai_agent/`: read-only evidence engine and approved troubleshooting guides.
- `apps/dashboard/`: React/TypeScript customer dashboard and browser tests.
- `simulator/fleet.py`: reproducible synthetic fleet and JSONL event output.
- `robotics/atlas_bridge/`: reliable transport core for the ROS 2 adapter.
- `robotics/atlas_ros/`: ROS 2 package, Nav2 action client, launch file, and configuration.
- `tests/test_api.py`: workflow and reliability tests.
- `tests/evaluations/`: reproducible synthetic incident evaluation dataset.
- `docs/architecture.md`: contracts, state handling, and design tradeoffs.
- `docs/requirements.md`: scope and next milestones.
- `docs/safety.md`: boundaries and approval model.
- `docs/evaluation.md`: tested behavior and limitations.

This is a local development prototype. A license and repository publication should be selected by the project owner before distributing it as open source.
