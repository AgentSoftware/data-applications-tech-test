"""Needs Postgres: docker compose up -d postgres, then pytest -m integration.

Uses its own database, psc_test (created if missing), so it never replaces the real psc data.
Override with PSC_TEST_DATABASE_URL.
"""
import json
import os
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
from psc_pipeline.__main__ import main  # noqa: E402

pytestmark = pytest.mark.integration
FIXTURES = Path(__file__).parent.parent / "fixtures"
SERVER = "postgresql://psc:psc@localhost:5432"
URL = os.environ.get("PSC_TEST_DATABASE_URL", f"{SERVER}/psc_test")


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    try:
        if "PSC_TEST_DATABASE_URL" not in os.environ:
            with psycopg.connect(f"{SERVER}/psc", connect_timeout=3, autocommit=True) as admin:
                if not admin.execute("SELECT 1 FROM pg_database WHERE datname = 'psc_test'").fetchone():
                    admin.execute("CREATE DATABASE psc_test")
        conn = psycopg.connect(URL, connect_timeout=3, autocommit=True)
    except psycopg.OperationalError as e:
        pytest.skip(f"no database: {e}")
    conn.execute("DROP SCHEMA IF EXISTS psc, psc_staging, psc_audit CASCADE")  # each test starts empty
    yield conn
    conn.close()


def one(conn, sql, *args):
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchone()


def test_publish_lookup_and_invariants(db):
    assert main(["--input", str(FIXTURES / "zz_example.jsonl")]) == 0
    payload = one(db, "SELECT payload FROM psc.psc_by_company WHERE company_number = %s", "ZZ000001")[0]
    assert payload == json.loads((FIXTURES / "zz_example_ZZ000001.json").read_text())
    # every company has exactly one serving row
    assert one(db, "SELECT count(*) FROM psc.company c LEFT JOIN psc.psc_by_company p USING (company_number) "
                   "WHERE p.company_number IS NULL")[0] == 0
    # every link that was not followed has a data_issue row in the same run
    assert one(db, """SELECT count(*) FROM psc.ownership_link l WHERE l.link_status <> 'followed'
                      AND NOT EXISTS (SELECT 1 FROM psc_audit.data_issue i WHERE i.run_id = l.run_id
                                      AND i.source_line = l.source_line AND i.check_code = l.link_status)""")[0] == 0
    assert last_run(db) == ("succeeded", ["duplicate_record", "non_uk_registration", "registration_number_normalised",
                                          "snapshot_stale", "unfollowed_share_high"])
    # the same file again: published, with a warning
    assert main(["--input", str(FIXTURES / "zz_example.jsonl")]) == 0
    assert "snapshot_already_loaded" in last_run(db)[1]


def last_run(conn):
    """(run_status, sorted check codes) of the latest run."""
    return one(conn, """SELECT r.run_status, coalesce(array_agg(i.check_code ORDER BY i.check_code)
                                FILTER (WHERE i.check_code IS NOT NULL), '{}')
                        FROM psc_audit.pipeline_run r LEFT JOIN psc_audit.data_issue i USING (run_id)
                        WHERE r.run_id = (SELECT max(run_id) FROM psc_audit.pipeline_run) GROUP BY 1""")


def test_failed_run_keeps_last_published_data(db, tmp_path):
    assert main(["--input", str(FIXTURES / "zz_example.jsonl")]) == 0
    no_trailer = tmp_path / "no-trailer.jsonl"
    no_trailer.write_text("".join((FIXTURES / "zz_example.jsonl").read_text().splitlines(True)[:-1]))
    assert main(["--input", str(no_trailer)]) == 1
    assert one(db, "SELECT count(*) FROM psc.psc_by_company")[0] == 3  # previous run still served
    assert one(db, "SELECT run_status, failure_reason FROM psc_audit.pipeline_run ORDER BY run_id DESC LIMIT 1") \
        == ("failed", "trailer_missing")


def test_missing_input_is_recorded(db):
    assert main(["--input", "/nonexistent.jsonl"]) == 1
    assert one(db, "SELECT run_status, failure_reason FROM psc_audit.pipeline_run ORDER BY run_id DESC LIMIT 1") \
        == ("failed", "input_missing")


def test_second_run_is_refused_while_one_holds_the_lock(db):
    with psycopg.connect(URL) as other:
        other.execute("SELECT pg_advisory_lock(7301001)")
        assert main(["--input", str(FIXTURES / "zz_example.jsonl")]) == 1
    assert one(db, "SELECT run_status, failure_reason FROM psc_audit.pipeline_run ORDER BY run_id DESC LIMIT 1") \
        == ("failed", "run_in_progress")
    assert main(["--input", str(FIXTURES / "zz_example.jsonl")]) == 0  # lock released with the connection


def test_older_snapshot_never_replaces_newer(db, tmp_path):
    assert main(["--input", str(FIXTURES / "zz_example.jsonl")]) == 0
    older = tmp_path / "older.jsonl"
    older.write_text((FIXTURES / "zz_example.jsonl").read_text().replace("2026-10-29", "2026-10-22"))
    assert main(["--input", str(older)]) == 1
    assert last_run(db)[0] == "failed" and "snapshot_not_newer" in last_run(db)[1]
    assert one(db, "SELECT max(run_id) FROM psc.psc_by_company")[0] == 1  # still run 1's data
