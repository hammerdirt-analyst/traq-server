# Technical Note: Postgres CI Integration Lane

## Why this branch exists

This branch exists to close the current testing gap between CI and production by
adding a PostgreSQL-backed integration lane to GitHub Actions.

The repo currently has strong test coverage and now has stronger release gates,
but most automated checks still run against SQLite while production runs on
PostgreSQL with Alembic migrations.

## Intentions and scope

1. Add a CI job that boots temporary PostgreSQL for test execution.
2. Run `alembic upgrade head` against that temporary database.
3. Execute a focused integration subset against PostgreSQL.
4. Keep the lane targeted so it adds parity value without making CI
   unnecessarily heavy.

## Explicitly out of scope

- Changing Cloud Run deployment architecture.
- Replacing the current fast SQLite-based regression lane.
- Expanding into a full matrix of all database backends.

## Expected outcomes

- Better pre-merge detection of Postgres-specific regressions.
- Earlier visibility into migration/runtime incompatibilities.
- Clearer separation between fast regression checks and database-parity checks.
