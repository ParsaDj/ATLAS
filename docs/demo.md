# Failure demonstration

This is the recommended two-minute ATLAS portfolio demonstration. It uses one
synthetic robot and the real API, database, authorization, incident,
investigation, maintenance, and audit workflows.

## Run it

```sh
docker compose up --build -d db api
docker compose --profile demo run --rm failure-demo
```

Expected checkpoints:

```text
[1/7] MISSION APPROVED     Robot 3 · <mission ID>
[2/7] FAILURE INJECTED    sensor_status=failed · <event ID>
[3/7] INCIDENT CREATED    sensor_failure · <incident ID>
[4/7] EVIDENCE CORRELATED 3 exact citations
[5/7] INVESTIGATION       supported · <investigator version>
[6/7] LIMITATION          <what the evidence cannot establish>
[7/7] HUMAN APPROVAL REQUIRED ticket <ticket ID> · draft
```

The default run intentionally stops at a draft maintenance ticket. To show the
explicit server-side approval transition in a fresh demonstration, run:

```sh
docker compose --profile demo run --rm -e ATLAS_DEMO_APPROVE=1 failure-demo
```

This produces `HUMAN APPROVED` at checkpoint seven and writes separate ticket
creation and approval records to the audit log. The environment option is the
operator's explicit action; investigation output still has no write tool.

Open [http://127.0.0.1:8000](http://127.0.0.1:8000), sign in with the local demo
account, and select **Incidents** to inspect the same records visually.

## What to show in a portfolio video

1. Begin with the seven terminal checkpoints for immediate context.
2. Open Robot 3 and show its `attention` state and failed mission.
3. Open the sensor incident and its exact triggering event.
4. Run the investigation and show the mission, event, and approved document
   citations.
5. Point out the limitation that prevents ATLAS from claiming an unsupported
   hardware root cause.
6. Show that the ticket begins in `draft`, then perform the explicit approval.
7. Open the audit history and show the distinct actor-attributed actions.

## Claims this demonstration supports

- Authenticated telemetry is stored and linked to operational state.
- One injected sensor observation produces one failed mission and one incident.
- The investigation cites the triggering event, mission, and approved document.
- The explanation records uncertainty instead of inventing a hardware cause.
- Maintenance creation and approval remain separate audited server workflows.

It does not establish physical robot safety, real-fleet reliability, or
general-purpose model accuracy.
