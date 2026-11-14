# Persons with Significant Control

A sample of the Companies House Persons with Significant Control (PSC) snapshot, and a Helm chart to run a pipeline over it on Kubernetes.

This repository is the starting point for a technical exercise. **Your task is described in [`TASK.md`](TASK.md).** This README covers what's here and what you need.

## Requirements

- Python 3.11 or later, and the SQL engine of your choice if you want one
- Docker
- Helm 3
- Optional: a local Kubernetes cluster such as [kind](https://kind.sigs.k8s.io/), k3d or minikube, and kubectl, to check your chart

## How it's laid out

```
data/
  persons-with-significant-control-snapshot-2026-10-29-sample.txt.gz   The raw sample: gzip, JSON lines
  README.md                                                             Where the data comes from, and its licence
kubernetes/helm/
  psc-pipeline/                                                         The chart for Part 2 of the task
artifacts/                                                              You fill this in: plans, prompts, session logs
NOTES.md                                                                You fill this in: your notes
REVIEW.md                                                               You fill this in: your review of the chart
TASK.md                                                                 The task
```

There is no starter code for the pipeline. Choose your own tools and layout.

### The data

The sample holds about 48,000 records for about 29,000 companies, in the format Companies House publishes the full snapshot. Each line is one JSON record. See [`data/README.md`](data/README.md).

### The chart

`kubernetes/helm/psc-pipeline/` is an umbrella chart: a weekly CronJob for the pipeline, and PostgreSQL from the [groundhog2k `postgres` chart](https://github.com/groundhog2k/helm-charts/tree/master/charts/postgres) as a dependency. Part 2 of the task is about this chart.

## Running the solution

### Run the pipeline locally (Docker Compose)

```
git clone <this repository> && cd data-applications-tech-test
docker compose up -d postgres
docker compose run --rm --build pipeline      # parses data/, runs the checks, publishes to Postgres
```

The run prints a quality summary and exits 0 when it published, 1 when a check failed (nothing published), 2 on any other error.

### Look up one company

```
docker compose exec postgres psql -U psc -d psc -c \
  "SELECT jsonb_pretty(payload) FROM psc.psc_by_company WHERE company_number = '04555610'"
```

What the checks found: `psc_audit.pipeline_run` (one row per run) and `psc_audit.data_issue` (one row per finding), for example
`SELECT check_code, action, count(*) FROM psc_audit.data_issue WHERE run_id = (SELECT max(run_id) FROM psc_audit.pipeline_run) GROUP BY 1, 2 ORDER BY 3 DESC;`

### Without Docker (Python 3.11+)

```
python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
pytest                                                    # unit tests, no database needed
python -m psc_pipeline --input data/persons-with-significant-control-snapshot-2026-10-29-sample.txt.gz --dry-run
pytest -m integration   # needs the compose Postgres; uses its own psc_test database
```

### Deploy with the chart

_To do in Part 2._

Design notes: [`artifacts/`](artifacts/) (specs, plans and one ADR per decision).

---

Your task: **[`TASK.md`](TASK.md)**.
