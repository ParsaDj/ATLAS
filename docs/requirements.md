# Scope and roadmap

ATLAS supports a fictional single facility, one customer, and five synthetic inspection robots. The operational goal is to create a mission, observe execution, identify failures, and retrieve the supporting event history.

## First milestone delivered

- Five seeded robots with status, position, battery, last contact, and mission linkage.
- Five-second synthetic telemetry and saved JSONL events.
- Low battery, sensor failure, and missing-heartbeat fault scenarios.
- Validated mission creation, explicit approval/state transitions, and cancellation with a reason.
- Persistent telemetry and incident APIs with retry deduplication and filtered, paginated evidence history.
- Local SQLite setup, PostgreSQL Compose configuration, and automated workflow tests.

## Remaining roadmap from the project blueprint

1. October–November 2026: harden the synthetic fleet/backend; verify PostgreSQL, normalize schema and add migrations.
2. December 2026–January 2027: React/TypeScript fleet, missions, events, and incidents dashboard.
3. February–March 2027: read-only AI investigation, document retrieval, evidence citations, and at least 100 held-out incident scenarios.
4. April–June 2027: ROS 2/Gazebo/Nav2 integration, starting with one robot.
5. July–August 2027: authenticated approvals, maintenance tickets, rescheduling, reports, audit logs, and recovery testing.
6. September 2027: reproducible portfolio release and recorded demo.

Budget: 5–7 hours/week, no hardware required. Milestones 1–3 form the MVP. Use only synthetic or appropriately licensed public material. Choose a license and publish the repository when ready; neither publication nor an open-source license is implied by this initial local scaffold.
