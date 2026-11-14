# 0015: Database credentials in the chart

- Status: Accepted (2026-11-14)
- Related: [plan 03](../plans/03-part2-helm-chart.md), [REVIEW.md](../../REVIEW.md) #2, #3 and #9

## Context

As received, the chart has the passwords in plain text in values.yaml, and the full `DATABASE_URL`, password included, in a ConfigMap. The Postgres values also used the wrong keys, so no password reached Postgres at all. The user asked for "no fancy features" for secrets.

## Options

1. Keep a URL, but move it into a Secret.
2. One chart-owned Secret holding the password. The pipeline gets `PGPASSWORD` from it with `secretKeyRef`, and the host, port, user and database as plain `PG*` env vars (libpq reads them, and `db.connect()` already supports them).
3. An external secret manager (External Secrets, or Secret Manager CSI on GKE).

## Decision

Option 2, plus `database.existingSecret` for people who make their own Secret.

- If `database.existingSecret` is empty, the chart creates `<fullname>-db`, with the key `password`. A password set in values wins. Otherwise the chart generates a 24-character random password, and on upgrade reads the existing Secret (with `lookup`), so the password doesn't change under a running database.
- The same Secret is passed to the groundhog2k subchart through `userDatabase.existingSecret`, so Postgres and the pipeline can't disagree. The superuser password lives in a second key of the same Secret.
- No password is ever in a ConfigMap, a URL or the rendered command line.

## Consequences

- `helm template` (no cluster) prints a new random password each time. That's expected; only a real install keeps it.
- Helm stores the rendered Secret in its release record. That's the same exposure as any Secret in the namespace, and RBAC on Secrets controls it.
- An external secret manager is the production answer (NOTES), not this chart's.
