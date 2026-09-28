# Scope and roadmap

ATLAS supports a fictional single facility, one customer, and five synthetic inspection robots. The operational goal is to create a mission, observe execution, identify failures, and retrieve the supporting event history.

## First milestone delivered

- Five seeded robots with status, position, battery, last contact, and mission linkage.
- Five-second synthetic telemetry and saved JSONL events.
- Low battery, sensor failure, and missing-heartbeat fault scenarios.
- Validated mission creation, explicit approval/state transitions, and cancellation with a reason.
- Persistent telemetry and incident APIs with retry deduplication and filtered, paginated evidence history.
- Deterministic read-only incident investigation with approved guide retrieval, citations, and uncertainty.
- A reproducible 120-scenario investigation evaluation dataset.
- Versioned Alembic migrations for fresh and legacy SQLite/PostgreSQL databases.
- Local SQLite setup, PostgreSQL Compose configuration, and automated workflow tests.

## Remaining roadmap from the project blueprint

1. Harden the synthetic fleet/backend: normalize frequently queried fields and add foreign keys and indexes.
2. Add an optional hosted-model renderer and versioned prompts while preserving the current evidence contract.
3. Integrate ROS 2/Gazebo/Nav2, starting with one robot.
4. Add authenticated approvals, maintenance tickets, rescheduling, reports, audit logs, and recovery testing.
5. Prepare a reproducible portfolio release and recorded demo.

Budget: 5–7 hours/week, no hardware required. Milestones 1–3 form the MVP. Use only synthetic or appropriately licensed public material. Choose a license and publish the repository when ready; neither publication nor an open-source license is implied by this initial local scaffold.

## Dashboard milestone delivered ahead of the target schedule

React/TypeScript overview, five-robot fleet cards, last-reported position plot, mission history and proposal form, explicit approvals/cancellations, incident history, evidence details, event timelines, and incident investigation are implemented. Desktop and mobile workflows use the live API. Five Playwright tests verify key customer workflows.

## Mission execution connected

The operations worker now executes dashboard-approved missions, reports waypoint progress, responds to cancellation, and resumes committed progress after short restarts. A missed heartbeat beyond the failure threshold remains a terminal failure requiring a new mission. Five browser tests cover the customer workflows, including real worker execution.

## Investigation milestone delivered

The first investigation service uses a deterministic evidence engine so the feature remains free and reproducible. It receives only API-authorized records, retrieves approved local troubleshooting guides, and returns cited findings with confidence, limitations, next steps, and a read-only tool trace. The 120-case dataset covers low battery, sensor failure, and heartbeat loss. Unknown faults and missing records produce insufficient-evidence results. An LLM renderer can be added later without changing these server-side boundaries.
