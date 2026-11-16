import subprocess
import sys

from psc_pipeline.__main__ import parse_args


def test_args_defaults():
    args = parse_args(["--input", "x.gz"])
    assert args.input == "x.gz" and args.dry_run is False


def test_dry_run_from_env(monkeypatch):
    monkeypatch.setenv("PSC_DRY_RUN", "true")
    assert parse_args(["--input", "x.gz"]).dry_run is True


def test_module_runs():
    out = subprocess.run([sys.executable, "-m", "psc_pipeline", "--help"], capture_output=True, text=True)
    assert out.returncode == 0 and "--input" in out.stdout
