# Review: `kubernetes/helm/psc-pipeline`

This reviews the chart as received (commit `fork/main`), as I would review a teammate's pull request. I read the rendered output (`helm template`) and the subchart's own source (groundhog2k `postgres` 1.1.8), not only the templates. Then I installed it unchanged on a local kind cluster:

- `helm install` fails: `env[name="PSC_DRY_RUN"].value: expected string` (#1).
- With only that patched in a scratch copy: `psc-postgres-0` goes into `CrashLoopBackOff` ("superuser password is not specified", #2), the job's wait loop prints `nc: bad address 'postgres'` forever (#3), and the ConfigMap is created in `default` while everything else is in the release namespace (#4).

**Verdict: request changes.** The chart can't run as written. Six separate problems each stop it: Kubernetes rejects the manifest, Postgres doesn't start, the job waits for a host that doesn't exist, the ConfigMap is missing outside the `default` namespace, the image can't be pulled, and the input is unreliable. Beyond those, it gives the pipeline cluster-admin and a privileged root container, stores passwords in plain text, allows two runs at once, and keeps the database on a disk that is gone after any restart.

Severity: **blocker** = install or run fails; **high** = security risk, or data loss or corruption; **medium** = wrong in some cases; **low** = tidiness.

| # | Problem | Where | How much it matters | What I changed |
|---|---|---|---|---|
| 1 | `PSC_DRY_RUN` renders as `value: false`, a YAML boolean. An env value must be a string, so the API server rejects the CronJob and `helm install` fails. | `cronjob.yaml` | blocker | |
| 2 | The `postgres:` values use **Bitnami** key names (`auth.username`, `auth.password`, `auth.database`, `auth.postgresPassword`, `primary.persistence`). The dependency is groundhog2k's chart, which uses `settings.superuserPassword.value`, `userDatabase.{name,user,password}.value` and `storage.requestedSize`. Helm ignores unknown keys without a warning. So no superuser password is set, the `postgres` image refuses to start without one, and no `psc` user or database would be created anyway. | `values.yaml` | blocker | |
| 3 | The database host is hardcoded as `postgres`, in the URL, in the wait loop and in NOTES. The subchart's Service is called `<release>-postgres` (for example `psc-postgres`). The `wait-for-postgres` loop has no time limit, so the pod sits in `Init` forever. | `_helpers.tpl`, `cronjob.yaml`, `NOTES.txt` | blocker | |
| 4 | The ConfigMap hardcodes `namespace: default`, while everything else goes to the release namespace. With `-n anything-else`, `envFrom` can't find it and the pod fails with `CreateContainerConfigError`. | `configmap.yaml` | blocker | |
| 5 | The image is `psc-pipeline:latest` with `pullPolicy: Always`. The name isn't in any registry, and `Always` stops a locally loaded image (kind, minikube) from being used. Result: `ImagePullBackOff`. `latest` also means you can't tell which code ran. | `values.yaml`, `Chart.yaml` | blocker | |
| 6 | The input only works for one week. The URL and `--input` both have a fixed date (`2026-10-29`), so every later run reloads that same old snapshot, or fails once Companies House removes the file. The download really works today: on kind it fetched a 2.4 GB zip holding `persons-with-significant-control-snapshot-2026-10-29.txt` (13.9 GB). But the zip is never deleted, so each run needs about 16.3 GB of disk, and nothing checks that the file is complete or recent. The pipeline also isn't built for the full snapshot: it holds the parsed records in memory (214 MB for the 48k-line sample, so tens of GB for 16 million records). | `cronjob.yaml`, `values.yaml` | blocker (from the second week) | |
| 7 | The ServiceAccount is bound to the **`cluster-admin` ClusterRole** across the whole cluster. The comment says the pipeline "reads its configuration from the cluster". It doesn't: it never calls the Kubernetes API. Anyone who can run code in this pod, for example through a malicious input or a compromised image, owns the cluster. | `clusterrolebinding.yaml` | high | |
| 8 | The container runs `privileged: true` as `runAsUser: 0`. Writing to a volume doesn't need either. Privileged mode turns off almost all container isolation (host devices, every capability). Our image is built to run as uid 10001. | `values.yaml` | high | |
| 9 | Passwords are in plain text in `values.yaml` (`psc-password-123`, `postgres`). The full `DATABASE_URL`, password included, is in a **ConfigMap**, which is meant for non-secret settings and is readable by anyone who can read ConfigMaps. The values file also ends up in Helm's release history. | `values.yaml`, `configmap.yaml`, `_helpers.tpl` | high | |
| 10 | `concurrencyPolicy: Allow`. If a run is late or slow and the next one starts, both build `psc_staging` and swap schemas at the same time and break each other. A manual `kubectl create job --from=cronjob/...` (which NOTES recommends) bypasses any CronJob policy anyway. | `values.yaml` | high | |
| 11 | Postgres persistence is turned off ("the pipeline rebuilds the tables on every run"). That's not true. The published tables are rebuilt, but `psc_audit` (run history and every data issue) isn't. And after any Postgres pod restart, eviction or node drain, the service has **no data until next week's run**. (The `primary.persistence` key is also a Bitnami key, so it does nothing; see #2. groundhog2k's chart also defaults to no volume.) | `values.yaml` | high | |
| 12 | `restartPolicy: OnFailure` with `backoffLimit: 10`. When the data checks fail, the pipeline exits 1, and the same input fails the same way every time. So it is restarted 10 times, each try adds a failed run to the audit, and because the container restarts in the same pod, earlier logs are lost. `OnFailure` also re-runs the download init container. | `cronjob.yaml`, `values.yaml` | medium | |
| 13 | No `activeDeadlineSeconds` and no `startingDeadlineSeconds`. A hung run (see the endless wait loop in #3) never ends. With a `Forbid` policy, it would then block every later week. | `cronjob.yaml` | medium | |
| 14 | No resource requests or limits. The scheduler can put the pod on a full node, and a memory spike can take the node down instead of only the pod. I measured the pipeline on the sample at a 214 MB peak. | `values.yaml` | medium | |
| 15 | Images aren't pinned (`busybox:latest`, the pipeline at `latest`). The subchart's default Postgres is **13.22**, which went end of life in Nov 2025, while the pipeline is built and tested on 16. | `cronjob.yaml`, `values.yaml` | medium | |
| 16 | The `helm test` pod runs `wget` against `<fullname>:80` (`.Values.service.port`). There is no Service, because this isn't a web app, so `helm test` always fails and tests nothing useful. | `templates/tests/test-connection.yaml` | medium | |
| 17 | The 50Gi `ReadWriteOnce` PVC always exists, only to hold a download that is used once. It costs money every week, and a RWO disk ties every run to the node that holds it. | `pvc.yaml`, `values.yaml` | low | |
| 18 | Leftover values from the web-app template: `replicaCount`, `service`, `ingress`, `autoscaling`. `LOG_LEVEL` isn't read by the pipeline. Leftovers mislead the next reader. | `values.yaml`, `configmap.yaml` | low | |
| 19 | The schedule comment ("after Companies House publishes the new snapshot") has no source, and without `timeZone` the time depends on the controller's clock. | `values.yaml` | low | |
| 20 | NOTES.txt gives the wrong Service name, and a `psql` line with no password, so neither works. | `NOTES.txt` | low | |
| 21 | `Chart.lock` is committed but `charts/` isn't, so `helm install` from a clean clone fails until you run `helm repo add groundhog2k https://groundhog2k.github.io/helm-charts/` and `helm dependency build`. Neither step is documented. | `Chart.yaml`, README | low | |

## What survives what

This was asked for in review: does the data survive a failure? With the chart as received, the answer is no. There's no volume, so **any** Postgres restart loses everything. After the fixes:

| Failure | Published data (`psc`) | Run history (`psc_audit`) |
|---|---|---|
| Pipeline pod fails mid-run | kept: the swap is one transaction, so the last good data stays | kept, plus a `failed` row |
| Postgres pod restarts | kept (PVC) | kept (PVC) |
| Node lost | kept if the storage class is network-attached (GKE Persistent Disk); lost on kind's node-local disk | same |
| `helm uninstall` | the StatefulSet's PVC is not deleted by Helm, so it's kept | same |
| Cluster lost | lost, but it can be rebuilt by re-running the job on the snapshot | **lost**: needs backups or managed Postgres (not in this chart) |

## Not fixed, and why

| Item | Why not |
|---|---|
| | |
