# Operational boundaries

ATLAS is an independent synthetic-data portfolio prototype. It does not connect to physical robots or proprietary systems. Its tests make no claims about physical safety.

The current API has no authentication. Run it only on the local loopback interface using the documented setup. The mission approval and cancellation endpoints enforce state transitions but does not yet authenticate the approver. Authentication and authorization are prerequisites for remote deployment and any agent-initiated write workflow.

The incident investigator has read-only access to API-supplied telemetry, mission records, and approved local documentation. It cites record and document identifiers, expresses uncertainty, and treats missing referenced evidence as insufficient. Its tool trace contains only record retrieval and document retrieval operations. It has no database connection, write tools, ticket access, mission transition access, or robot control path.

Ticket creation and rescheduling require authenticated server-side approval before those capabilities are added. A future language model renderer must preserve the same server-enforced evidence and authorization boundary. No model receives direct motor controls or the ability to override safety rules.
