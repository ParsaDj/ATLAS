# Security policy

## Supported version

ATLAS is a pre-1.0 portfolio project. Security fixes are applied to the latest
commit on `main`; older commits and local deployments are not maintained as
separate supported versions.

## Reporting a vulnerability

Do not open a public issue for a vulnerability that could expose credentials,
sessions, or deployment data. Use GitHub's private vulnerability reporting for
this repository. Include the affected endpoint or component, reproduction
steps, expected impact, and any suggested mitigation. Reports involving only
synthetic demo data may be filed as normal issues when they contain no secrets.

ATLAS is designed for synthetic simulation and portfolio demonstrations. It is
not a physical robot safety controller and has not been certified for industrial
deployment.

## Deployment expectations

Internet-facing deployments must use HTTPS, secure cookies, unique secrets,
restricted database access, and a reverse proxy or managed gateway that applies
network-level rate limits. Demo credentials in repository configuration are not
production credentials. Set `ATLAS_ENVIRONMENT=production` to enable startup
guards for the database, public URL, cookie settings, and core credentials.
These checks do not replace the review in
[`docs/deployment-security.md`](docs/deployment-security.md).
