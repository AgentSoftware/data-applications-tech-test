# Plan 03: Part 2, review and fix the Helm chart

Status: approved 2026-11-14, with these changes after the Helm Q&A:

- **Advisory lock in the pipeline.** `concurrencyPolicy: Forbid` covers only scheduled runs; a manual `kubectl create job --from=cronjob/...` or a second release bypasses it. Each writing run takes `pg_try_advisory_lock` and stops with exit 1 and `run_in_progress` if another run holds it.
- **Downloads go to an `emptyDir`**, not a PVC. The input is fetched fresh each run, so it needs no disk. pvc.yaml is removed.
- **"What survives what"** goes in `REVIEW.md` and the chart NOTES: a pod restart, a node loss, an uninstall, a cluster loss.
- Tools: helm and kind installed with Homebrew. The chart's default input is the sample baked into the image.
- `REVIEW.md` is written against the chart as received. The as-received chart stays at `fork/main` in git. Commits are made only with approval.

## 0. Goal

1. Write `REVIEW.md` against the chart **as received**, before changing anything. The as-received chart is in git at `fork/main`, so the review can always be checked against it.
2. Change the chart so that `helm install` on a clean cluster runs our pipeline and writes `psc.psc_by_company`. Check it on a local kind cluster.
3. In `REVIEW.md`, say for every problem what changed, or why it was not fixed.

Out of scope: the production design (that goes in `NOTES.md`, which the user writes), HA Postgres, and a real weekly download from Companies House.

## 1. What I checked before planning

- The subchart is groundhog2k `postgres` 1.1.8. I downloaded it into the scratchpad and read its `values.yaml` and templates. Its keys are `settings.superuserPassword.value`, `userDatabase.{name,user,password}.value` and `storage.requestedSize`. The chart's `postgres.auth.*` and `postgres.primary.persistence` are **Bitnami keys**, so the subchart silently ignores them.
- The subchart's Service is called `<release>-postgres`, not `postgres`.
- The subchart's default image is Postgres **13.22**, which is end of life. Compose and our tests use 16.
- Full-sample run: 2.0 s and a **214 MB** peak RSS (measured with `/usr/bin/time -l`, as a dry run).
- Tools: `kubectl` is installed; `helm` and `kind` are not.

## 2. Problems found (the draft of `REVIEW.md`)

Severity: **blocker** = install or run fails; **high** = security risk or data loss; **medium** = wrong behaviour in some cases; **low** = tidiness.

| # | Problem | Where | Severity | Planned fix |
|---|---|---|---|---|
| 1 | `PSC_DRY_RUN` is rendered as `value: false`, a YAML boolean. Kubernetes rejects it, because an env value must be a string. | cronjob.yaml | blocker | `| quote` |
| 2 | The subchart values use Bitnami keys (`auth.*`, `primary.persistence`). They are ignored, so there is no superuser password and the `postgres` container exits on start. No `psc` user or database is created either. | values.yaml | blocker | Use the groundhog2k keys (`settings`, `userDatabase`, `storage`). |
| 3 | The host `postgres` is hardcoded in the DB URL, the wait loop and NOTES. The real Service is `<release>-postgres`, so the wait loop never ends and the job hangs. | _helpers.tpl, cronjob.yaml, NOTES.txt | blocker | Use a helper that builds the Service name, plus a `database.host` value for an external database. |
| 4 | The ConfigMap hardcodes `namespace: default`. Installing in any other namespace means `envFrom` can't find it, so the pod fails with CreateContainerConfigError. | configmap.yaml | blocker | Remove the line (Helm sets the namespace). |
| 5 | The image `psc-pipeline:latest` is pulled with `pullPolicy: Always`, but it isn't in any registry. Result: ImagePullBackOff. | values.yaml | blocker | Pin a tag (`0.1.0`), use `IfNotPresent`, and document `kind load docker-image`. |
| 6 | The input is wrong in three ways. The init container downloads a fixed-date URL, so it is stale after one week. The pipeline reads a file name that may not be in the zip. The real snapshot is many GB and is split into parts. Nothing checks the download. | cronjob.yaml, values.yaml | blocker | By default, run on the sample baked into the image (`/app/data/...sample.txt.gz`). Keep a download init container as an **opt-in** (`input.download.enabled`), with `wget` failing on errors, unzip to a known name, and a set path. See ADR 0014. |
| 7 | The `helm test` pod `wget`s `<fullname>:80`, but there is no Service. `.Values.service.port` belongs to a web-app template. So `helm test` always fails. | tests/test-connection.yaml | medium | Replace it with a test pod that runs `psql`: `SELECT count(*) FROM psc.psc_by_company` > 0. |
| 8 | The ServiceAccount is bound to **cluster-admin** for the whole cluster. The comment ("reads its configuration from the cluster") is false: the pipeline never calls the Kubernetes API. | clusterrolebinding.yaml | high | Delete the binding, and set `automountServiceAccountToken: false`. |
| 9 | The container runs `privileged: true` as `runAsUser: 0`. Nothing needs it, and our image runs as 10001. | values.yaml | high | `runAsNonRoot`, uid 10001, `allowPrivilegeEscalation: false`, drop ALL capabilities, `readOnlyRootFilesystem`, seccomp `RuntimeDefault`. Add `fsGroup` for the optional data volume. |
| 10 | The DB passwords sit in plain text in values.yaml (`psc-password-123`, `postgres`), and `DATABASE_URL`, password included, is in a **ConfigMap**. | values.yaml, configmap.yaml | high | Put the password in a Secret, or use an `existingSecret`. The pipeline reads `PG*` variables (PGPASSWORD from `secretKeyRef`), so no URL holds the password. If no password is given, generate one with `randAlphaNum` and keep it across upgrades with `lookup`. See ADR 0015. |
| 11 | `concurrencyPolicy: Allow` lets two runs build `psc_staging` at the same time and break each other. | values.yaml | high | `Forbid`, plus a Postgres advisory lock in the pipeline for manual jobs. |
| 12 | Postgres has **no volume** ("the pipeline rebuilds the tables"). Not true: `psc_audit` keeps run history, and after any pod restart the service is empty until the next weekly run. | values.yaml | high | `storage.requestedSize: 2Gi` |
| 13 | `backoffLimit: 10` with `restartPolicy: OnFailure` retries a failed data check (exit 1, which fails the same way every time) ten times. Each try adds a failed audit row, and the restarts overwrite the logs. | cronjob.yaml, values.yaml | medium | `restartPolicy: Never`, `backoffLimit: 2`, and a `podFailurePolicy` with exit code 1 → `FailJob` (don't retry a data failure; retry exit code 2 or a lost pod). |
| 14 | There is no `activeDeadlineSeconds`, and the wait loop has no timeout, so a stuck run hangs forever and `Forbid` then blocks every later run. | cronjob.yaml | medium | `activeDeadlineSeconds: 3600`, and a time limit on the wait loop. |
| 15 | No resources are set. The pipeline holds the snapshot in memory (214 MB for the sample). | values.yaml | medium | Request 256Mi / 250m, limit 512Mi. Comment that the full snapshot needs a different design, not a bigger pod. |
| 16 | Images aren't pinned: `busybox:latest`, `appVersion: latest`, pipeline `latest`. Postgres is 13 (end of life). | Chart.yaml, cronjob.yaml, values.yaml | medium | Pin `busybox:1.36`, `appVersion: "0.1.0"`, and Postgres image tag `16.4`. |
| 17 | A 50Gi RWO PVC is always created and kept, and is only needed for downloads. | pvc.yaml, values.yaml | low | Remove it. A download goes to an `emptyDir` that lasts only for the run. |
| 18 | Dead values from the web-app template: `service`, `ingress`, `autoscaling`, `replicaCount`. `LOG_LEVEL` isn't read by the pipeline. | values.yaml | low | Remove them. |
| 19 | The schedule comment ("after Companies House publishes") isn't backed up, and the CronJob runs in the controller's time zone. | values.yaml | low | Add `timeZone: Etc/UTC` and an honest comment. Keep the weekly schedule. |
| 20 | NOTES.txt has the wrong Service name, and its `psql` line can't log in. | NOTES.txt | low | Fix it, and add a lookup query. |
| 21 | `Chart.lock` exists but `charts/` doesn't, so a fresh clone needs `helm dependency build`. That isn't documented. | README | low | Document it in README. Don't commit the tarball. |

Not fixing (will be said in `REVIEW.md`): a real weekly download of the full 15 GB snapshot (production design, NOTES), HA or managed Postgres (in production it would be Cloud SQL), NetworkPolicy, and an external secret manager.

## 3. Build steps

1. **Review first:** write `REVIEW.md` from table 2 against the untouched chart (problem, where, severity; the "what I changed" column comes later). Commit it on its own, so the review is clearly done before the fixes.
2. **ADRs:** 0014 (the chart's input: baked-in sample by default, download as opt-in) and 0015 (DB credentials: Secret plus `PG*` variables, with a generated password by default).
3. **Chart fixes 1–21:** small edits to the existing templates; no new abstractions.
4. **Static checks:** `helm dependency build`, `helm lint`, `helm template`, and a `helm template` run with download enabled and with an external database.
5. **kind check:** create a cluster, `docker build -t psc-pipeline:0.1.0 .`, `kind load docker-image`, `helm install`, `kubectl create job --from=cronjob/...`, wait for it to finish, `helm test`, then look up `04555610`. Then run it a second time to show that a re-run swaps the data and adds to `psc_audit`.
6. Fill in the "What I changed" column of `REVIEW.md` and the README "Deploy with the chart" section.

## 4. How you can test it

```
brew install helm kind
helm dependency build kubernetes/helm/psc-pipeline
helm lint kubernetes/helm/psc-pipeline
kind create cluster --name psc
docker build -t psc-pipeline:0.1.0 . && kind load docker-image psc-pipeline:0.1.0 --name psc
helm install psc kubernetes/helm/psc-pipeline --wait
kubectl create job --from=cronjob/psc-psc-pipeline psc-manual && kubectl wait --for=condition=complete job/psc-manual --timeout=300s
kubectl logs job/psc-manual          # the run summary
helm test psc
```

## 5. Questions (answered 2026-11-14)

1. helm and kind with Homebrew: yes.
2. Baked-in sample as the default input, with the download as an opt-in: yes.

## 6. Build notes (2026-11-14)

- Installing the chart as received on kind confirmed #1–#4. It also corrected two guesses in the first draft: the fixed URL does exist today (a 2.4 GB zip holding a 13.9 GB `.txt` with the expected name), so #6 is a "from the second week" blocker about the date, the disk and the size, not a wrong file name.
- The subchart's values can't be templated from the parent chart, so the Secret has a fixed name (`database.secretName`, default `psc-db`), repeated in `postgres.settings/userDatabase.existingSecret`. secret.yaml fails the render if they differ.
- The Secret is kept on uninstall (`helm.sh/resource-policy: keep`). Without that, a reinstall would generate a new password that doesn't match the kept Postgres volume.
- The ConfigMap template was removed, not fixed: plain env vars plus `secretKeyRef` are simpler.
- The download path was tested with a zip of the sample served from the host (`host.docker.internal`), not a real Companies House download.

## 7. Follow-up approved 2026-11-14 (after the "anything dodgy?" questions)

1. **Subchart 1.1.8 → 1.4.12.** It ships Postgres 16.14, the same major version as Compose and the tests, so there's no image override on a chart built for 13. The value keys are unchanged (checked by diffing the two `values.yaml` files).
2. **Wait for Postgres with `pg_isready`** (postgres image) instead of a TCP check with `nc`.
3. **Notes on the limits:** `lookup` and GitOps renders (set a password or `existingSecret`); one release per namespace (fixed Secret name); `postgres.fullnameOverride` isn't supported; bump the image tag on each build.
4. **Chart tests in the repo:** `tests/chart/test_render.py` (pytest, `helm template`, skips without helm; PyYAML added to the dev extra) and `tests/chart/test_kind.py` (marker `kind`, opt-in), which replays the manual kind checks.
5. **Freshness and completeness checks** in the pipeline: ADR 0012 amendment. `snapshot_not_newer`, `snapshot_already_loaded`, `snapshot_stale`, `company_count_drop`, all in `run_checks`, with unit tests. `db.last_published()` reads the last published run.
