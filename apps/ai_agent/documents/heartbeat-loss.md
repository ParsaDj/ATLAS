# Robot heartbeat loss

Document ID: DOC-CONNECTION-001

A missed heartbeat supports a communications or process-availability failure.
Check the robot process and network path, then require a fresh heartbeat before
creating a replacement mission. A timeout has no triggering telemetry event,
so it cannot establish why the robot stopped reporting.
