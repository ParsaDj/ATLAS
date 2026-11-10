# Deployment security

ATLAS has an explicit production configuration mode that rejects several unsafe
startup combinations. It is a guardrail for operators, not a claim that the
portfolio application is certified or ready for an industrial deployment.

## Local demo and production mode

| Control | Development default | Production mode |
| --- | --- | --- |
| Database | SQLite or PostgreSQL | PostgreSQL required |
| Public URL | Optional | HTTPS URL required |
| Session cookie | May be sent over HTTP | Secure flag required |
| Bridge credential | Optional; ingestion fails closed | Strong, non-demo value required |
| Bootstrap password | Required only when no user exists | Placeholder values rejected when configured |

The Docker Compose stack explicitly uses development mode and binds the API to
localhost. Its checked-in credentials exist only to make the synthetic demo
reproducible.

## Enable production guards

Generate secrets with a password manager or platform secret manager. Do not
commit their values.

```sh
export ATLAS_ENVIRONMENT=production
export DATABASE_URL='postgresql+psycopg://atlas@database.example/atlas'
export ATLAS_PUBLIC_URL='https://atlas.example.com'
export ATLAS_SECURE_COOKIES=1
export ATLAS_TELEMETRY_API_KEY='a-unique-random-value-with-at-least-32-characters'
```

## Rotate the bridge credential

ATLAS accepts one active telemetry key and, temporarily, one previous key. This
allows bridges with a durable outbox to move to a new credential without an
ingestion outage:

1. Generate a new random value with at least 32 characters.
2. Set `ATLAS_TELEMETRY_API_KEY` to the new value and
   `ATLAS_TELEMETRY_PREVIOUS_API_KEY` to the key being retired.
3. Restart the API, then update and restart each bridge with the new active key.
4. Confirm every bridge can poll its mission and flush its outbox.
5. Remove `ATLAS_TELEMETRY_PREVIOUS_API_KEY` and restart the API again.

Both keys receive the same facility-wide bridge permissions during the overlap.
Production guards reject short, placeholder, or identical rotation keys. ATLAS
compares every configured candidate in constant time and never returns which key
matched. A previous key is an emergency rotation window, not a second permanent
credential.

On the first start of a new database, also provide a unique bootstrap password
with at least 16 characters. Remove it from the runtime environment after the
administrator has been created.

Production mode stops during application construction when the database is not
PostgreSQL, the public URL is not HTTPS, secure cookies are disabled, the bridge
key is missing or too short, or a configured secret contains a known demo or
placeholder marker. Normal minimum-length validation still applies in every
environment.

## Deployment review checklist

Before exposing ATLAS beyond a controlled demonstration:

- terminate TLS at a maintained proxy or gateway and restrict allowed hosts;
- keep credentials in a managed secret store, define rotation, and use a
  separate credential for each robot or bridge identity when that identity
  model is introduced;
- restrict database network access, encrypt backups, and test restoration;
- replace local accounts with managed identity, MFA, recovery, and offboarding;
- move login throttling and heartbeat monitoring to shared services before
  adding API workers;
- export audit records to tamper-resistant storage with retention controls;
- redact telemetry and model inputs, define retention, and review any external
  model provider's data handling terms;
- monitor readiness, failed authentication, ingestion lag, incident creation,
  and outbox replay; and
- keep motor control and physical safety enforcement outside ATLAS.

The threat boundaries and current adversarial coverage are described in
[security/threat-model.md](security/threat-model.md). Physical safety limits are
described in [safety.md](safety.md).
