"""Render the chart with `helm template` and check what REVIEW.md depends on (no cluster needed).

Needs helm and the subchart: helm repo add groundhog2k https://groundhog2k.github.io/helm-charts/
                             helm dependency build kubernetes/helm/psc-pipeline
The numbers (#n) are the findings in REVIEW.md.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")
CHART = Path(__file__).parents[2] / "kubernetes" / "helm" / "psc-pipeline"
pytestmark = pytest.mark.skipif(not shutil.which("helm") or not list((CHART / "charts").glob("postgres-*.tgz")),
                                reason="needs helm and `helm dependency build`")


def render(*sets):
    args = ["helm", "template", "psc", str(CHART)] + [a for s in sets for a in ("--set", s)]
    out = subprocess.run(args, capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(out.stderr)
    return [d for d in yaml.safe_load_all(out.stdout) if d]


def of_kind(docs, kind):
    return [d for d in docs if d["kind"] == kind]


def pod_spec(docs):
    [cron] = of_kind(docs, "CronJob")
    return cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]


def containers(spec):
    return spec.get("initContainers", []) + spec["containers"]


@pytest.fixture(scope="module")
def docs():
    return render()


def test_env_values_are_strings(docs):  # 1
    for spec in [pod_spec(docs)] + [d["spec"]["template"]["spec"] for d in of_kind(docs, "StatefulSet")]:
        for c in containers(spec):
            for e in c.get("env", []):
                assert "value" not in e or isinstance(e["value"], str), (c["name"], e)


def test_postgres_and_pipeline_share_one_secret(docs):  # 2, 9
    [sts] = of_kind(docs, "StatefulSet")
    pg = {e["name"]: e for e in sts["spec"]["template"]["spec"]["containers"][0]["env"]}
    for name in ("POSTGRES_PASSWORD", "POSTGRES_DB", "USERDB_USER", "USERDB_PASSWORD"):
        assert pg[name]["valueFrom"]["secretKeyRef"]["name"] == "psc-db"
    env = {e["name"]: e for e in pod_spec(docs)["containers"][0]["env"]}
    assert env["PGPASSWORD"]["valueFrom"]["secretKeyRef"] == {"name": "psc-db", "key": "USERDB_PASSWORD"}
    [secret] = of_kind(docs, "Secret")
    assert set(secret["data"]) == {"POSTGRES_DB", "USERDB_USER", "USERDB_PASSWORD", "POSTGRES_PASSWORD"}


def test_no_password_outside_the_secret(docs):  # 9
    assert not of_kind(docs, "ConfigMap") or all(d["metadata"]["name"].startswith("psc-postgres")
                                                 for d in of_kind(docs, "ConfigMap"))  # only the subchart's scripts
    text = yaml.safe_dump([d for d in docs if d["kind"] != "Secret"])
    assert "DATABASE_URL" not in text and "psc-password-123" not in text


def test_pipeline_points_at_the_real_service(docs):  # 3
    [svc] = of_kind(docs, "Service")
    env = {e["name"]: e.get("value") for e in pod_spec(docs)["containers"][0]["env"]}
    assert env["PGHOST"] == svc["metadata"]["name"] == "psc-postgres"


def test_no_hardcoded_namespace(docs):  # 4
    assert [d["metadata"]["name"] for d in docs if "namespace" in d["metadata"]] == []


def test_images_are_pinned(docs):  # 5, 15
    spec = pod_spec(docs)
    images = [c["image"] for c in containers(spec)]
    assert all(":" in i and not i.endswith(":latest") for i in images), images
    assert spec["containers"][0]["imagePullPolicy"] == "IfNotPresent"


def test_no_rbac_and_no_token(docs):  # 7
    assert not [d for d in docs if d["kind"] in ("ClusterRoleBinding", "RoleBinding", "ClusterRole", "Role")]
    [sa] = [d for d in of_kind(docs, "ServiceAccount") if d["metadata"]["name"] == "psc-psc-pipeline"]
    assert sa["automountServiceAccountToken"] is False and pod_spec(docs)["automountServiceAccountToken"] is False


def test_not_root_not_privileged(docs):  # 8
    spec = pod_spec(docs)
    assert spec["securityContext"]["runAsNonRoot"] is True and spec["securityContext"]["runAsUser"] == 10001
    for c in containers(spec):
        sc = c["securityContext"]
        assert not sc.get("privileged") and sc["allowPrivilegeEscalation"] is False
        assert sc["readOnlyRootFilesystem"] is True and sc["capabilities"]["drop"] == ["ALL"]


def test_one_run_at_a_time_and_no_blind_retries(docs):  # 10, 12, 13
    [cron] = of_kind(docs, "CronJob")
    job = cron["spec"]["jobTemplate"]["spec"]
    assert cron["spec"]["concurrencyPolicy"] == "Forbid"
    assert job["template"]["spec"]["restartPolicy"] == "Never" and job["backoffLimit"] == 2
    assert job["activeDeadlineSeconds"] == 3600
    [stop] = [r for r in job["podFailurePolicy"]["rules"] if r["action"] == "FailJob"]
    assert stop["onExitCodes"] == {"containerName": "pipeline", "operator": "In", "values": [1]}


def test_postgres_has_a_volume_and_pipeline_has_none(docs):  # 11, 17
    [sts] = of_kind(docs, "StatefulSet")
    [claim] = sts["spec"]["volumeClaimTemplates"]
    assert claim["spec"]["resources"]["requests"]["storage"] == "2Gi"
    assert of_kind(docs, "PersistentVolumeClaim") == []
    assert [v["name"] for v in pod_spec(docs)["volumes"]] == ["tmp"]


def test_resources_set(docs):  # 14
    r = pod_spec(docs)["containers"][0]["resources"]
    assert r["requests"]["memory"] == "256Mi" and r["limits"]["memory"] == "512Mi"


def test_default_input_is_the_baked_in_sample(docs):  # 6
    spec = pod_spec(docs)
    assert spec["containers"][0]["args"] == ["--input", "/app/data/persons-with-significant-control-snapshot-2026-10-29-sample.txt.gz"]
    assert [c["name"] for c in spec["initContainers"]] == ["wait-for-postgres"]


def test_helm_test_checks_the_output(docs):  # 16
    [pod] = [d for d in of_kind(docs, "Pod") if d["metadata"]["annotations"].get("helm.sh/hook") == "test"]
    assert "psc.psc_by_company" in pod["spec"]["containers"][0]["command"][-1]


def test_download_is_opt_in_into_scratch_space():  # 6, 17
    spec = pod_spec(render("input.download.enabled=true", "input.download.url=https://example.test/s.zip",
                           "input.path=/input/s.txt"))
    assert [c["name"] for c in spec["initContainers"]] == ["download-snapshot", "wait-for-postgres"]
    [vol] = [v for v in spec["volumes"] if v["name"] == "input"]
    assert vol == {"name": "input", "emptyDir": {"sizeLimit": "20Gi"}}
    assert spec["containers"][0]["args"] == ["--input", "/input/s.txt"]


def test_external_database():
    docs = render("postgres.enabled=false", "database.host=db.example")
    assert not of_kind(docs, "StatefulSet")
    env = {e["name"]: e.get("value") for e in pod_spec(docs)["containers"][0]["env"]}
    assert env["PGHOST"] == "db.example"


@pytest.mark.parametrize("sets, message", [
    (["postgres.enabled=false"], "set database.host"),
    (["database.secretName=other"], "must equal database.secretName"),
    (["input.download.enabled=true"], "input.download.url is required"),
])
def test_misconfiguration_fails_with_a_message(sets, message):
    with pytest.raises(RuntimeError, match=message):
        render(*sets)
