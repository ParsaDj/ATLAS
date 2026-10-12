# Changelog

All notable changes to ATLAS are documented here. The project follows
[Semantic Versioning](https://semver.org/); dates refer to published releases.

## [Unreleased]

- Validate the ROS 2 Jazzy/Nav2 adapter with one Gazebo Harmonic robot.
- Publish results from the frozen benchmark against a named live model.
- Record the narrated two-minute portfolio walkthrough.

## [0.1.0] - Pending

### Added

- Five-robot synthetic inspection fleet with deterministic low-battery, sensor,
  and connectivity failures.
- FastAPI and PostgreSQL operations API with Alembic migrations, authenticated
  telemetry, explicit mission transitions, incident workflows, maintenance
  approvals, replacement missions, and audit history.
- React and TypeScript dashboard covering fleet status, mission operations,
  incident evidence, investigations, technical documents, users, and reports.
- Evidence-grounded deterministic investigator and optional model adapter with
  a closed response schema, citation allowlisting, provenance, and safe fallback.
- ROS-independent bridge core, durable SQLite outbox, and ROS 2/Nav2 adapter.
- Structured logs, metrics, readiness checks, build provenance, optional trace
  export, production configuration guards, and a tested threat model.
- Reproducible failure demonstration, load framework, evaluation datasets, and
  automated browser evidence capture.

### Reliability evidence

- 254 Python tests, including PostgreSQL and SQLite behavior.
- 120 deterministic investigation cases and a frozen 12-case live-model suite.
- 50 generated state-machine traces and 10 browser workflows.
- Docker Compose build, restart-recovery, and telemetry smoke verification in CI.

### Known limits

- The ROS 2 adapter has unit and contract coverage; Gazebo runtime acceptance
  still requires Ubuntu 24.04, ROS 2 Jazzy, Gazebo Harmonic, and Nav2.
- No live-model benchmark result is published yet.
- ATLAS is a single-host portfolio demonstration and is not a physical safety
  controller or a validated production fleet deployment.

[Unreleased]: https://github.com/ParsaDj/ATLAS/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ParsaDj/ATLAS/releases/tag/v0.1.0
