"""Entry point: python -m psc_pipeline --input <snapshot> [--dry-run].

Exit codes: 0 published (or dry run passed), 1 a check failed and nothing was published, 2 any other error.
"""
import argparse
import hashlib
import os
import sys
import traceback
from pathlib import Path

from .build import build_payloads, run_checks, summary
from .graph import build_ancestors, classify_links, owner_map
from .parse import Issue, parse_file


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="psc_pipeline", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, help="path to the snapshot (.txt.gz or .txt)")
    p.add_argument("--dry-run", action="store_true",
                   default=os.environ.get("PSC_DRY_RUN", "").lower() == "true",
                   help="run every check but write nothing (or PSC_DRY_RUN=true)")
    return p.parse_args(argv)


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def process(path):
    """Everything except the database: returns (parsed, tables, issues, failed check codes)."""
    parsed = parse_file(path)
    issues = parsed.issues
    companies = {r["company_number"] for r in parsed.psc + parsed.statements + parsed.exemptions}
    links = classify_links(parsed.psc, companies, issues)
    ancestors = build_ancestors(companies, owner_map(links), issues)
    payloads, statuses = build_payloads(parsed, links, ancestors, issues)
    failed = run_checks(parsed, links, payloads, issues)
    tables = {
        "company": [{"company_number": c, "control_status": s} for c, s in sorted(statuses.items())],
        "psc": parsed.psc, "psc_statement": parsed.statements, "psc_exemption": parsed.exemptions,
        "ownership_link": links, "company_ancestor": ancestors,
        "psc_by_company": [{"company_number": c, "payload": p} for c, p in sorted(payloads.items())],
    }
    return parsed, tables, issues, failed


def main(argv=None) -> int:
    args = parse_args(argv)
    path = Path(args.input)
    conn = run_id = None
    try:
        if not args.dry_run:
            from . import db  # psycopg is only needed when writing
            conn = db.connect()
            run_id = db.start_run(conn, str(path), sha256(path) if path.is_file() else None, args.dry_run)

        if not path.is_file() or path.stat().st_size == 0:
            issues = [Issue("input_missing", "error", "rejected", details={"path": str(path)})]
            if conn:
                db.finish_run(conn, run_id, "failed", "input_missing", None, None, issues)
            print(f"PSC pipeline: FAILED (input missing or empty: {path})", file=sys.stderr)
            return 1

        parsed, tables, issues, failed = process(path)
        published = False
        if conn:
            if not failed:
                db.publish(conn, run_id, tables)
                published = True
            db.finish_run(conn, run_id, "failed" if failed else "succeeded", ", ".join(failed) or None,
                          parsed, len(tables["company"]), issues)
        print(summary(run_id, parsed, issues, failed, published, len(tables["company"])))
        return 1 if failed else 0
    except Exception:
        traceback.print_exc()
        if conn and run_id:
            try:
                conn.rollback()
                db.finish_run(conn, run_id, "failed", "error: " + traceback.format_exc(limit=1)[-500:],
                              None, None, [])
            except Exception:
                pass
        return 2
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
