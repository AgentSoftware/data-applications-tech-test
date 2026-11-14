"""Serving payload per company, run checks and summary. Rules: spec 02 sections 3.4, 5, 6; ADRs 0003, 0004, 0007, 0012."""
from collections import Counter, defaultdict

from .normalise import normalise_number
from .parse import Issue


def _clean(d: dict) -> dict:
    """Drop None and empty values (but always keep via and levels); dates become ISO strings."""
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v)
            for k, v in d.items() if k in ("via", "levels") or (v is not None and v != [] and v != {})}


def build_payloads(parsed, links, ancestors, issues) -> tuple[dict, dict]:
    """Returns ({company_number: payload}, {company_number: control_status})."""
    psc_by_company, st_by_company, ex_by_company = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in parsed.psc:
        if r["is_active"]:
            psc_by_company[r["company_number"]].append(r)
    for r in parsed.statements:
        if r["is_active"]:
            st_by_company[r["company_number"]].append(r)
    for r in parsed.exemptions:
        ex_by_company[r["company_number"]].append(r)
    link_of = {l["source_line"]: l for l in links}
    issues_of = defaultdict(list)
    for i in issues:
        if i.severity == "info":  # data_quality shows warnings and errors only; all issues stay in data_issue
            continue
        companies = i.details["companies"] if i.check_code == "cycle" else [i.company_number]
        for cn in companies:
            if cn:
                issues_of[cn].append(i.check_code)
    by_start = defaultdict(list)
    for a in ancestors:
        by_start[a["company_number"]].append(a)

    payloads, statuses = {}, {}
    for start, reached in by_start.items():
        level_of = {a["ancestor_company_number"]: a["level"] for a in reached}
        levels = defaultdict(lambda: defaultdict(list))
        for a in reached:
            cn, lvl = a["ancestor_company_number"], a["level"]
            common = {"company_number": cn, "via": a["via_company_numbers"], "route_count": a["route_count"]}
            out = levels[lvl]
            for r in psc_by_company[cn]:
                entry = _entry(r, link_of.get(r["source_line"]), common, lvl, level_of)
                out[entry[0]].append((r["source_line"], entry[1]))
            for r in st_by_company[cn]:
                out["statements"].append((r["source_line"], _clean(
                    {"statement_code": r["statement_code"], "notified_on": r["notified_on"]} | common)))
            for r in ex_by_company[cn]:
                out["exemptions"].append((r["source_line"], _clean({"exemption_details": r["exemption_details"]} | common)))

        payload_levels = []
        for lvl in sorted(levels):
            lists = {name: [e for _, e in sorted(entries, key=lambda x: x[0])]
                     for name, entries in levels[lvl].items() if entries}
            if lists:
                payload_levels.append({"level": lvl} | {k: lists[k] for k in LIST_ORDER if k in lists})
        status = control_status(levels.get(0, {}))
        codes = [c for cn in level_of for c in issues_of.get(cn, [])]
        payloads[start] = _clean({
            "company_number": start,
            "snapshot_date": parsed.snapshot_date,
            "control_status": status,
            "levels": payload_levels,
            "data_quality": {"issue_count": len(codes), "check_codes": sorted(set(codes))} if codes else None,
        })
        statuses[start] = status
    return payloads, statuses


LIST_ORDER = ("people", "protected", "companies", "other_controllers", "unfollowed", "statements", "exemptions")


def _entry(r, link, common, lvl, level_of):
    t = r["psc_type"]
    if t == "individual":
        return "people", _clean({"name": r["name"], "kind": r["kind"], "birth_year": r["birth_year"],
                                 "birth_month": r["birth_month"], "natures_of_control": r["natures_of_control"],
                                 "notified_on": r["notified_on"]} | common)
    if t == "super_secure":
        return "protected", _clean({"kind": r["kind"], "description": r["description"]} | common)
    if t == "legal_person":
        return "other_controllers", _clean({"name": r["name"], "kind": r["kind"], "legal_form": r["legal_form"],
                                            "natures_of_control": r["natures_of_control"],
                                            "notified_on": r["notified_on"]} | common)
    if link and link["link_status"] == "followed":
        owner = link["owner_company_number"]
        seen_at = level_of.get(owner)
        return "companies", _clean({
            "name": r["name"], "owner_company_number": owner, "natures_of_control": r["natures_of_control"],
            "notified_on": r["notified_on"],
            "already_at_level": seen_at if seen_at is not None and seen_at <= lvl else None,
            "not_expanded": "depth_cap" if seen_at is None else None} | common)
    return "unfollowed", _clean({"name": r["name"], "kind": r["kind"],
                                 "registration_number_raw": r["registration_number_raw"],
                                 "country_registered": r["country_registered"],
                                 "reason": link["link_status"] if link else None} | common)


def control_status(level0) -> str:
    if any(level0.get(k) for k in ("people", "protected", "companies", "other_controllers", "unfollowed")):
        return "ok"
    if level0.get("exemptions"):
        return "exempt"
    if level0.get("statements"):
        return "psc_statement_only"
    return "no_active_psc"


# --- Run checks and summary (spec 02 section 3.4 and 6; ADR 0012) ---------------------------

MAX_MALFORMED_SHARE = 0.001     # fail above 0.1% of lines
MAX_TRAILER_GAP_SHARE = 0.001   # fail above 0.1% of a trailer count; warn on any gap
MAX_UNFOLLOWED_SHARE = 0.15     # warn above 15% of active corporate links
TRAILER_KEYS = {"psc": "persons_of_significant_control_count", "statement": "statements_count",
                "exemption": "exemptions_count"}


def run_checks(parsed, links, payloads, issues) -> list[str]:
    """Adds run-level issues; returns the check codes that fail the run."""
    failed = []

    def add(code, severity, fails=False, **details):
        issues.append(Issue(code, severity, "flagged", details=details or None))
        if fails:
            failed.append(code)

    if parsed.trailer is None:
        add("trailer_missing", "error", True)
    else:
        for group, key in TRAILER_KEYS.items():
            expected = parsed.trailer.get(key)
            if not isinstance(expected, int):
                add("trailer_count_mismatch", "error", True, group=group, trailer=expected, reason="no count")
                continue
            gap = expected - parsed.distinct_by_group[group] - parsed.malformed_by_group[group]
            if gap:
                too_big = abs(gap) > MAX_TRAILER_GAP_SHARE * max(expected, 1)
                add("trailer_count_mismatch", "error" if too_big else "warning", too_big,
                    group=group, trailer=expected, parsed=parsed.distinct_by_group[group],
                    malformed=parsed.malformed_by_group[group], gap=gap)
    malformed = sum(parsed.malformed_by_group.values())
    if parsed.line_count and malformed > MAX_MALFORMED_SHARE * parsed.line_count:
        add("malformed_share_exceeded", "error", True, malformed=malformed, lines=parsed.line_count)
    if links:
        unfollowed = sum(l["link_status"] != "followed" for l in links)
        if unfollowed > MAX_UNFOLLOWED_SHARE * len(links):
            add("unfollowed_share_high", "warning", unfollowed=unfollowed, links=len(links))
    bad_keys = [k for k in payloads if normalise_number(k) != k]
    if bad_keys:
        add("unreachable_serving_key", "error", True, examples=bad_keys[:10], count=len(bad_keys))
    if not payloads:
        add("empty_output", "error", True)
    return failed


def summary(run_id, parsed, issues, failed, published, company_count) -> str:
    state = "SUCCEEDED (published)" if published else ("FAILED (nothing published)" if failed
                                                       else "SUCCEEDED (dry run, nothing written)")
    t = parsed.trailer or {}
    recon = "  ".join(
        f"{g} {t.get(k)} vs {parsed.distinct_by_group[g]:,} + {parsed.malformed_by_group[g]} malformed"
        for g, k in TRAILER_KEYS.items())
    counts = Counter((i.check_code, i.action) for i in issues)
    lines = [f"PSC pipeline {f'run {run_id}' if run_id is not None else 'dry run'}: {state}",
             f"snapshot {parsed.snapshot_date}  lines {parsed.line_count:,}  "
             f"records {sum(parsed.distinct_by_group.values()):,}  companies {company_count:,}",
             f"reconciliation  {recon}",
             "issues by check_code and action:"]
    lines += [f"  {code:34} {action:13} {n:>7,}" for (code, action), n in sorted(counts.items())]
    lines.append("fail rules: " + (", ".join(failed) if failed else "all passed"))
    return "\n".join(lines)
