# Operational boundaries

ATLAS is an independent synthetic-data portfolio prototype. It does not connect to physical robots or proprietary systems. Its tests make no claims about physical safety.

The local application authenticates human users with server-side sessions and enforces roles for mission and administrative actions. Mission approvals, cancellations, investigations, and user creation are attributed in the audit log. Secure cookies can be enabled with `ATLAS_SECURE_COOKIES=1` when TLS is present. Robot producers use a separate bridge key; missing or incorrect credentials cannot ingest telemetry. Remote deployment still requires TLS, managed secrets, rotation, per-robot identity, rate limiting, and account recovery.

AI investigation output never creates maintenance work. An operator or administrator must draft and separately approve a ticket. The assigned technician must explicitly start and resolve it. Server-side state validation and audit records enforce these boundaries independently of dashboard controls.

Downloaded reports escape stored values before rendering and clearly label investigation findings, confidence, limitations, and citations. They are authenticated and audited, but remain synthetic operational summaries rather than safety certifications or maintenance authorizations.

The incident investigator has read-only access to API-supplied telemetry, mission records, and approved local documentation. It cites record and document identifiers, expresses uncertainty, and treats missing referenced evidence as insufficient. Its tool trace contains only record retrieval and document retrieval operations. It has no database connection, write tools, ticket access, mission transition access, or robot control path.

Ticket creation and rescheduling require authenticated server-side approval before those capabilities are added. A future language model renderer must preserve the same server-enforced evidence and authorization boundary. No model receives direct motor controls or the ability to override safety rules.
