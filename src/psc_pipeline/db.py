"""Postgres: audit rows, COPY into psc_staging, then swap it in as psc (ADR 0002).

Connection: DATABASE_URL, or the standard libpq variables (PGHOST, PGUSER, PGPASSWORD, ...).
"""
import os
from dataclasses import asdict
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

SQL = Path(__file__).parent / "sql"

COLUMNS = {
    "company": ["company_number", "control_status", "run_id"],
    "psc": ["source_line", "line_hash", "company_number", "company_number_raw", "kind", "psc_type", "name",
            "birth_year", "birth_month", "natures_of_control", "notified_on", "ceased_on", "ceased_on_raw",
            "is_active", "registration_number_raw", "registration_number", "country_registered",
            "place_registered", "legal_form", "description", "self_link", "run_id"],
    "psc_statement": ["source_line", "line_hash", "company_number", "company_number_raw", "statement_code",
                      "notified_on", "ceased_on", "ceased_on_raw", "is_active", "self_link", "run_id"],
    "psc_exemption": ["source_line", "line_hash", "company_number", "company_number_raw", "exemption_details",
                      "self_link", "run_id"],
    "ownership_link": ["source_line", "owned_company_number", "owner_company_number", "link_status", "run_id"],
    "company_ancestor": ["company_number", "ancestor_company_number", "level", "via_company_numbers",
                         "route_count"],
    "psc_by_company": ["company_number", "payload", "run_id"],
}
ISSUE_COLUMNS = ["run_id", "check_code", "severity", "action", "source_line", "company_number", "field_name",
                 "raw_value", "fixed_value", "details"]
JSON_COLUMNS = {"exemption_details", "payload", "details"}
RUN_LOCK = 7_301_001  # pg advisory lock key: one writing run at a time, however it was started


def connect():
    return psycopg.connect(os.environ.get("DATABASE_URL", ""))  # "" -> libpq reads PG* variables


def _copy(cur, table, columns, rows):
    with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as cp:
        for row in rows:
            cp.write_row([Jsonb(row.get(c)) if c in JSON_COLUMNS and row.get(c) is not None else row.get(c)
                          for c in columns])


def start_run(conn, source_file, sha256, dry_run) -> int:
    with conn.cursor() as cur:
        cur.execute((SQL / "audit.sql").read_text())
        cur.execute("INSERT INTO psc_audit.pipeline_run (source_file, source_sha256, dry_run) "
                    "VALUES (%s, %s, %s) RETURNING run_id", (source_file, sha256, dry_run))
        run_id = cur.fetchone()[0]
    conn.commit()
    return run_id


def try_lock(conn) -> bool:
    """Session lock, held until the connection closes; a second run gets False straight away."""
    got = conn.execute("SELECT pg_try_advisory_lock(%s)", (RUN_LOCK,)).fetchone()[0]
    conn.commit()
    return got


def last_published(conn):
    """The last run that published (succeeded, not a dry run), or None."""
    row = conn.execute("""SELECT snapshot_date, source_sha256, company_count FROM psc_audit.pipeline_run
                          WHERE run_status = 'succeeded' AND NOT dry_run ORDER BY run_id DESC LIMIT 1""").fetchone()
    conn.commit()
    return dict(zip(("snapshot_date", "source_sha256", "company_count"), row)) if row else None


def finish_run(conn, run_id, status, failure_reason, parsed, company_count, issues):
    with conn.cursor() as cur:
        _copy(cur, "psc_audit.data_issue", ISSUE_COLUMNS, ({"run_id": run_id, **asdict(i)} for i in issues))
        cur.execute(
            """UPDATE psc_audit.pipeline_run SET finished_at = now(), run_status = %s, failure_reason = %s,
                   snapshot_date = %s, line_count = %s, malformed_line_count = %s, duplicate_record_count = %s,
                   company_count = %s, trailer_counts = %s, parsed_counts = %s
               WHERE run_id = %s""",
            (status, failure_reason, parsed.snapshot_date if parsed else None,
             parsed.line_count if parsed else None,
             sum(parsed.malformed_by_group.values()) if parsed else None,
             parsed.duplicate_count if parsed else None, company_count,
             Jsonb(parsed.trailer) if parsed and parsed.trailer else None,
             Jsonb(dict(parsed.distinct_by_group)) if parsed else None, run_id))
    conn.commit()


def publish(conn, run_id, tables: dict):
    """Build every table in psc_staging, then replace psc in one transaction."""
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS psc_staging CASCADE; CREATE SCHEMA psc_staging; "
                    "SET LOCAL search_path TO psc_staging")
        cur.execute((SQL / "schema.sql").read_text())
        for table, columns in COLUMNS.items():  # dict order = foreign-key order
            _copy(cur, table, columns, ({"run_id": run_id, **r} for r in tables[table]))
        cur.execute("DROP SCHEMA IF EXISTS psc CASCADE; ALTER SCHEMA psc_staging RENAME TO psc")
    conn.commit()
