# Contributing

ATLAS accepts focused issues and pull requests that preserve its synthetic-data,
vendor-independent scope.

1. Create a branch from `main`.
2. Keep customer, employer, and real robot data out of code, fixtures, logs, and
   screenshots.
3. Add an Alembic revision for every schema change.
4. Run `.venv/bin/pytest -q` and the dashboard build before opening a pull
   request. Run the Playwright workflow for customer-facing changes.
5. Describe the operational behavior, validation, and limitations in the pull
   request.

Contributions are licensed under Apache-2.0. By submitting a contribution, you
agree that it may be distributed under that license.
