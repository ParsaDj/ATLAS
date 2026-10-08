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
- Immutable, approved technical-document revisions with stable version and content-hash citations.
- Versioned Alembic migrations for fresh and legacy SQLite/PostgreSQL databases.
- Local role-based authentication, CSRF protection, user administration, and audit history.
- Local SQLite setup, PostgreSQL Compose configuration, and automated workflow tests.

## Remaining roadmap from the project blueprint

1. Harden the synthetic fleet/backend: normalize frequently queried fields and add foreign keys and indexes.
2. Add an optional hosted-model renderer and versioned prompts while preserving the current evidence contract.
3. Validate the implemented ROS 2 adapter against one Gazebo/Nav2 robot, then execute approved waypoint missions end to end.
4. Expand recovery testing and operational measurements.
5. Prepare a reproducible portfolio release and recorded demo.

Budget: 5–7 hours/week, no hardware required. Milestones 1–3 form the MVP. Use only synthetic or appropriately licensed public material. Choose a license and publish the repository when ready; neither publication nor an open-source license is implied by this initial local scaffold.

## Dashboard milestone delivered ahead of the target schedule

React/TypeScript overview, five-robot fleet cards, last-reported position plot, mission history and proposal form, explicit approvals/cancellations, incident history, evidence details, event timelines, incident investigation, and a versioned technical-document library are implemented. Administrators draft and separately approve guidance; every authenticated role can inspect approved revisions. Desktop and mobile workflows use the live API. Ten Playwright tests verify key customer workflows.

## Mission execution connected

The operations worker now executes dashboard-approved missions, reports waypoint progress, responds to cancellation, and resumes committed progress after short restarts. A missed heartbeat beyond the failure threshold remains a terminal failure requiring a new mission. Five browser tests cover the customer workflows, including real worker execution.

## Investigation milestone delivered

The first investigation service uses a deterministic evidence engine so the feature remains free and reproducible. It receives only API-authorized records, retrieves approved document revisions from the application database, and returns cited findings with confidence, limitations, next steps, and a read-only tool trace. Revisions are immutable and citations include the exact version and SHA-256 content hash. Bundled Markdown revisions provide a local evaluation fallback. The 120-case dataset covers low battery, sensor failure, and heartbeat loss. Unknown faults and missing records produce insufficient-evidence results. An LLM renderer can be added later without changing these server-side boundaries.
