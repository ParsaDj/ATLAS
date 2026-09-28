# Operational boundaries

ATLAS is an independent synthetic-data portfolio prototype. It does not connect to physical robots or proprietary systems. Its tests make no claims about physical safety.

The current API has no authentication. Run it only on the local loopback interface using the documented setup. The mission approval and cancellation endpoints enforce state transitions but does not yet authenticate the approver. Authentication and authorization are prerequisites for remote deployment and any agent-initiated write workflow.

The future AI agent starts with read-only access to telemetry and approved documentation. It must cite evidence and express uncertainty. Ticket creation and rescheduling require authenticated server-side approval. The model never receives direct motor controls or the ability to override safety rules.
