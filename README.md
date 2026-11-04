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

_Replace this section with the exact commands to run your pipeline from a clean clone, to deploy it with your chart, and to look up one company in the output._

---

Your task: **[`TASK.md`](TASK.md)**.
