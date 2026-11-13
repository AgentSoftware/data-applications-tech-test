# 0006: Postgres locally with Docker Compose; kind only for the chart

- Status: Accepted (2026-11-13)
- Related: spec 00 Q1; [0002](0002-storage-clean-tables-plus-serving-table.md)

## Context

The output target is Postgres both locally and in the cluster. Reviewers need to run the pipeline from a clean clone. The README already lists Docker as a prerequisite.

## Options

1. Docker Compose: Postgres plus the pipeline image.
2. A local Postgres install.
3. A file output locally (SQLite or JSONL) behind the same interface.
4. A kind cluster for everything.

## Decision

Option 1.
- **`docker compose`:** a `postgres` service, plus a `pipeline` service built from the same Dockerfile the Helm chart uses, so the local run also tests the image.
- **pytest:** unit tests cover the pure Python logic (number normalisation, data checks, BFS, routes) and need no database. A small number of integration tests run against the Compose Postgres.
- **kind:** used only to check that the Part 2 chart installs and the CronJob writes its output.

## Consequences

- There's one storage engine, so local and cluster runs don't behave differently.
- Integration tests need Docker running. Unit tests don't.
- The README's "Running the solution" section will give exact Compose commands.
