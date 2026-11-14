"""Install the chart on a local kind cluster and check the behaviour REVIEW.md claims. Slow (a few minutes).

    kind create cluster --name psc
    pytest -m kind tests/chart/test_kind.py

Builds and loads the image, installs into a fresh namespace (psc-kind-test), and deletes the namespace at the end.
"""
import base64
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.kind
ROOT = Path(__file__).parents[2]
CHART = ROOT / "kubernetes" / "helm" / "psc-pipeline"
CLUSTER, NS, IMAGE = "psc", "psc-kind-test", "psc-pipeline:0.1.0"
CTX = f"kind-{CLUSTER}"


def sh(*args, check=True):
    out = subprocess.run(args, capture_output=True, text=True, timeout=600)
    if check and out.returncode:
        raise AssertionError(f"{' '.join(args)}\n{out.stdout}\n{out.stderr}")
    return out.stdout.strip()


def k(*args, check=True):
    return sh("kubectl", "--context", CTX, "-n", NS, *args, check=check)


def helm(*args):
    return sh("helm", *args, "-n", NS, "--kube-context", CTX)


def sql(query):
    return k("exec", "psc-postgres-0", "-c", "postgres", "--", "sh", "-c",
             f'PGPASSWORD=$USERDB_PASSWORD psql -h localhost -U psc -d psc -tAc "{query}"')


def run_job(name):
    k("create", "job", "--from=cronjob/psc-psc-pipeline", name)
    k("wait", "--for=condition=complete", f"job/{name}", "--timeout=300s")
    return k("logs", f"job/{name}", "-c", "pipeline")


def password():
    return base64.b64decode(k("get", "secret", "psc-db", "-o", "jsonpath={.data.USERDB_PASSWORD}")).decode()


@pytest.fixture(scope="module")
def release():
    if not all(shutil.which(t) for t in ("kind", "helm", "kubectl", "docker")):
        pytest.skip("needs kind, helm, kubectl and docker")
    if CLUSTER not in sh("kind", "get", "clusters").split():
        pytest.skip(f"no kind cluster '{CLUSTER}': kind create cluster --name {CLUSTER}")
    sh("docker", "build", "-q", "-t", IMAGE, str(ROOT))
    sh("kind", "load", "docker-image", IMAGE, "--name", CLUSTER)
    sh("kubectl", "--context", CTX, "delete", "namespace", NS, "--ignore-not-found", "--wait=true")
    helm("install", "psc", str(CHART), "--create-namespace", "--wait", "--timeout", "5m")
    yield
    sh("kubectl", "--context", CTX, "delete", "namespace", NS, "--wait=false")


def test_run_publishes_and_helm_test_passes(release):
    log = run_job("run1")
    assert "SUCCEEDED (published)" in log and "companies 29,125" in log and "fail rules: all passed" in log
    assert "psc_by_company rows: 29125" in helm("test", "psc", "--logs")
    assert sql("SELECT jsonb_array_length(payload->'levels') FROM psc.psc_by_company "
               "WHERE company_number = '04555610'") == "23"


def test_data_survives_a_postgres_restart(release):
    k("delete", "pod", "psc-postgres-0", "--wait=true")
    k("wait", "--for=condition=ready", "pod/psc-postgres-0", "--timeout=180s")
    assert sql("SELECT count(*) FROM psc.psc_by_company") == "29125"


def test_upgrade_keeps_the_password(release):
    before = password()
    helm("upgrade", "psc", str(CHART), "--wait")
    assert password() == before


def test_second_concurrent_run_is_refused_without_retries(release):
    k("create", "job", "--from=cronjob/psc-psc-pipeline", "a")
    k("create", "job", "--from=cronjob/psc-psc-pipeline", "b")
    for j in ("a", "b"):  # each ends complete or failed
        k("wait", "--for=jsonpath={.status.conditions[0].status}=True", f"job/{j}", "--timeout=300s")
    reasons = sorted(k("get", "job", j, "-o", "jsonpath={.status.conditions[-1].reason}") for j in ("a", "b"))
    assert reasons == ["CompletionsReached", "PodFailurePolicy"]
    assert sql("SELECT failure_reason FROM psc_audit.pipeline_run WHERE run_status = 'failed'") == "run_in_progress"


def test_uninstall_keeps_data_and_password_for_reinstall(release):
    before = password()
    helm("uninstall", "psc", "--wait")
    left = k("get", "pvc,secret", "-o", "name").split()
    assert "persistentvolumeclaim/postgres-data-psc-postgres-0" in left and "secret/psc-db" in left
    helm("install", "psc", str(CHART), "--wait", "--timeout", "5m")
    assert password() == before
    assert sql("SELECT count(*) FROM psc.psc_by_company") == "29125"
    assert "SUCCEEDED (published)" in run_job("after-reinstall")
