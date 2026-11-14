"""Stream the snapshot into clean rows plus data issues. Rules: spec 02 sections 1.3, 2 and 3.1."""
import gzip
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from .normalise import date_from_filename, normalise_number, parse_date

PSC_TYPES = {
    "individual-person-with-significant-control": "individual",
    "individual-beneficial-owner": "individual",
    "super-secure-person-with-significant-control": "super_secure",
    "corporate-entity-person-with-significant-control": "corporate",
    "corporate-entity-beneficial-owner": "corporate",
    "legal-person-person-with-significant-control": "legal_person",
    "legal-person-beneficial-owner": "legal_person",
}
STATEMENT = "persons-with-significant-control-statement"
EXEMPTIONS = "exemptions"
TRAILER_PREFIX = "totals#"
KIND_IN_TEXT = re.compile(r'"kind"\s*:\s*"([^"]+)"')


@dataclass
class Issue:
    check_code: str
    severity: str  # error | warning | info
    action: str    # rejected | dropped | fixed | flagged | not_followed
    source_line: int | None = None
    company_number: str | None = None
    field_name: str | None = None
    raw_value: str | None = None
    fixed_value: str | None = None
    details: dict | None = None


@dataclass
class Parsed:
    snapshot_date: date | None = None
    trailer: dict | None = None
    line_count: int = 0
    duplicate_count: int = 0
    distinct_by_group: Counter = field(default_factory=Counter)   # for reconciliation
    malformed_by_group: Counter = field(default_factory=Counter)  # group "unknown" if kind not recoverable
    psc: list = field(default_factory=list)
    statements: list = field(default_factory=list)
    exemptions: list = field(default_factory=list)
    issues: list = field(default_factory=list)


def group_of(kind: str | None) -> str:
    if kind in PSC_TYPES:
        return "psc"
    return {STATEMENT: "statement", EXEMPTIONS: "exemption"}.get(kind, "unknown")


def read_lines(path):
    """Yield (line_number, raw_bytes) without loading the file."""
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rb") as f:
        yield from enumerate(f, start=1)


def parse_file(path) -> Parsed:
    out = Parsed()
    first_line_of = {}  # line hash -> first line number (exact duplicates)
    by_self_link = {}   # links.self -> rows sharing it (conflicting duplicates)

    for n, raw in read_lines(path):
        out.line_count = n
        raw = raw.rstrip(b"\r\n")
        try:
            rec = json.loads(raw)
            if not isinstance(rec, dict) or not isinstance(rec.get("data"), dict):
                raise ValueError("not a {company_number, data} object")
        except (ValueError, UnicodeDecodeError) as e:
            m = KIND_IN_TEXT.search(raw.decode("utf-8", "replace"))
            out.malformed_by_group[group_of(m.group(1) if m else None)] += 1
            out.issues.append(Issue("malformed_json", "error", "rejected", n, details={"error": str(e)[:200]}))
            continue

        data = rec["data"]
        kind = data.get("kind")
        if isinstance(kind, str) and kind.startswith(TRAILER_PREFIX):
            if out.trailer is not None:
                out.issues.append(Issue("duplicate_trailer", "warning", "flagged", n))
            out.trailer = data  # the last trailer wins
            continue

        h = hashlib.blake2b(raw.rstrip(), digest_size=16).hexdigest()
        if h in first_line_of:
            out.duplicate_count += 1
            out.issues.append(Issue("duplicate_record", "info", "dropped", n,
                                    details={"duplicate_of_line": first_line_of[h]}))
            continue
        first_line_of[h] = n
        group = group_of(kind)
        out.distinct_by_group[group] += 1

        if group == "unknown":
            out.issues.append(Issue("unknown_kind", "error", "rejected", n, raw_value=str(kind)))
            continue
        raw_cn = rec.get("company_number")
        cn = normalise_number(raw_cn)
        if cn is None:
            code = "missing_company_number" if raw_cn in (None, "") else "unrecognised_company_number"
            out.issues.append(Issue(code, "error", "rejected", n, raw_value=None if raw_cn is None else str(raw_cn)))
            continue
        if cn != raw_cn:
            out.issues.append(Issue("company_number_normalised", "info", "fixed", n, cn,
                                    "company_number", raw_cn, cn))

        row = {"source_line": n, "line_hash": h, "company_number": cn, "company_number_raw": raw_cn,
               "self_link": (data.get("links") or {}).get("self")}
        if group == "exemption":
            row |= {"exemption_details": data.get("exemptions"), "is_active": True}
            out.exemptions.append(row)
        else:
            row |= dates(data, n, cn, out.issues)
            if group == "statement":
                row["statement_code"] = data.get("statement")
                out.statements.append(row)
            else:
                row |= psc_fields(data, kind)
                out.psc.append(row)
        if row["self_link"]:
            by_self_link.setdefault(row["self_link"], []).append((group, row))

    out.snapshot_date = snapshot_date(out, path)
    resolve_conflicts(out, by_self_link)
    if out.snapshot_date:
        for row in out.psc + out.statements:
            set_active(row, out.snapshot_date, out.issues)
        for row in out.psc:
            if row["is_active"]:
                person_checks(row, out.snapshot_date, out.issues)
    return out


def dates(data, n, cn, issues) -> dict:
    row = {"ceased_on_raw": data.get("ceased_on"), "notified_on_raw": data.get("notified_on")}
    for f in ("notified_on", "ceased_on"):
        value, issue = parse_date(data.get(f))
        if f == "notified_on" and data.get("kind") != "super-secure-person-with-significant-control" \
                and data.get(f) is None:
            issue = "invalid_date"  # required for everything except super-secure
        if issue == "date_timestamp_truncated":
            issues.append(Issue(issue, "info", "fixed", n, cn, f, str(data.get(f)), value.isoformat()))
        elif issue == "invalid_date":
            issues.append(Issue(issue, "warning", "flagged", n, cn, f, str(data.get(f))))
        row[f] = value
        row[f + "_invalid"] = issue == "invalid_date"
    return row


def psc_fields(data, kind) -> dict:
    ident = data.get("identification") or {}
    dob = data.get("date_of_birth") if isinstance(data.get("date_of_birth"), dict) else {}
    year, month = dob.get("year"), dob.get("month")
    if not (isinstance(year, int) and isinstance(month, int) and 1 <= month <= 12):
        year = month = None  # reported as missing_birth_date for active individuals
    return {
        "kind": kind,
        "psc_type": PSC_TYPES[kind],
        "name": data.get("name"),
        "birth_year": year,
        "birth_month": month,
        "natures_of_control": list(data.get("natures_of_control") or []),
        "registration_number_raw": ident.get("registration_number"),
        "country_registered": ident.get("country_registered"),
        "place_registered": ident.get("place_registered"),
        "legal_form": ident.get("legal_form"),
        "description": data.get("description"),
        "ceased_flag": data.get("ceased") is True,
    }


def snapshot_date(out: Parsed, path) -> date | None:
    from_file = date_from_filename(str(path))
    from_trailer, _ = parse_date(str((out.trailer or {}).get("generated_at") or "")[:10] or None)
    if from_trailer and from_file and from_trailer != from_file:
        out.issues.append(Issue("snapshot_date_mismatch", "warning", "flagged",
                                details={"trailer": from_trailer.isoformat(), "file_name": from_file.isoformat()}))
    return from_trailer or from_file


def resolve_conflicts(out: Parsed, by_self_link: dict) -> None:
    """Same links.self, different content: keep the ceased copy if exactly one is ceased, else the first."""
    drop = set()
    for link, entries in by_self_link.items():
        if len(entries) < 2:
            continue
        ceased = [r for _, r in entries if r.get("ceased_on") or r.get("ceased_flag")]
        keep = ceased[0] if len(ceased) == 1 else entries[0][1]
        for _, r in entries:
            kept = r is keep
            out.issues.append(Issue("conflicting_duplicate", "warning", "flagged" if kept else "dropped",
                                    r["source_line"], r["company_number"],
                                    details={"self_link": link, "kept_line": keep["source_line"]}))
            if not kept:
                drop.add(r["source_line"])
    if drop:
        for name in ("psc", "statements", "exemptions"):
            setattr(out, name, [r for r in getattr(out, name) if r["source_line"] not in drop])


def set_active(row, snap: date, issues) -> None:
    n, cn, notified, ceased = row["source_line"], row["company_number"], row["notified_on"], row["ceased_on"]
    if row.get("psc_type") == "super_secure":
        row["is_active"] = not row["ceased_flag"] and not row["ceased_on_invalid"] and (ceased is None or ceased > snap)
        return
    if notified and ceased and ceased < notified:
        issues.append(Issue("ceased_before_notified", "warning", "flagged", n, cn,
                            details={"notified_on": notified.isoformat(), "ceased_on": ceased.isoformat()}))
    if notified and notified > snap:
        issues.append(Issue("notified_after_snapshot", "warning", "flagged", n, cn, "notified_on", notified.isoformat()))
    row["is_active"] = (notified is not None and notified <= snap
                        and not row["ceased_on_invalid"]
                        and (ceased is None or ceased > snap)
                        and not (ceased and ceased < notified))


def person_checks(row, snap: date, issues) -> None:
    n, cn = row["source_line"], row["company_number"]
    if row["psc_type"] == "individual":
        y, m = row["birth_year"], row["birth_month"]
        if y is None or m is None:
            issues.append(Issue("missing_birth_date", "info", "flagged", n, cn))
        elif snap.year - y - ((snap.month, snap.day) < (m, 1)) < 16:
            issues.append(Issue("implausible_birth_date", "warning", "flagged", n, cn,
                                "date_of_birth", f"{y}-{m:02d}"))
    if row["psc_type"] != "super_secure" and not row["natures_of_control"]:
        issues.append(Issue("missing_natures_of_control", "info", "flagged", n, cn))
