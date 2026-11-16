#!/usr/bin/env python3
"""Streaming, read-only data profile of the Companies House PSC snapshot.

The gzipped JSON-lines file is read one line at a time and never held in memory.
The script keeps only:
  * counters,
  * a 16-byte hash per record, to find duplicates,
  * the company -> corporate-owner edge list, which is needed to trace chains.

Usage:
    python3 scripts/profile_data.py data/<snapshot>.txt.gz [--out report.md] [--trace 4]

The report is Markdown, written to stdout or to the --out path.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import date

# Patterns and reference values.
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T")
CANONICAL_CN_RE = re.compile(r"^(\d{8}|[A-Z]{2}\d{6})$")  # 01234567 or SC123456
KIND_IN_RAW_RE = re.compile(r'"kind"\s*:\s*"([^"]+)"')
SNAPSHOT_IN_NAME_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
UK_RE = re.compile(
    r"\b(england|wales|scotland|northern ireland|united kingdom|uk|u\.k\.|great britain|"
    r"britain|companies house|cardiff)\b",
    re.IGNORECASE,
)
PSC_REGIME_START = date(2016, 4, 6)  # the PSC register started on 6 April 2016

STATEMENT_KIND = "persons-with-significant-control-statement"
EXEMPTIONS_KIND = "exemptions"
TRAILER_PREFIX = "totals#"


def is_psc_kind(kind: str) -> bool:
    """Kinds that the trailer counts as 'persons of significant control'."""
    return kind != STATEMENT_KIND and (
        "person-with-significant-control" in kind or "beneficial-owner" in kind
    )


def is_corporate_kind(kind: str) -> bool:
    return kind.startswith("corporate-entity")


def is_individual_kind(kind: str) -> bool:
    return kind.startswith("individual")


def normalise_number(raw: object) -> tuple[str | None, str]:
    """Return (normalised value, format category) for a company or registration number.

    The category names every fix applied, joined with '+', or 'canonical' if none was needed.
    """
    if raw is None:
        return None, "missing"
    if not isinstance(raw, str):
        return None, f"not_string:{type(raw).__name__}"
    fixes = []
    value = raw
    if value != value.strip():
        fixes.append("whitespace")
        value = value.strip()
    if value != value.upper():
        fixes.append("lowercase")
        value = value.upper()
    if value.isdigit() and len(value) < 8:
        fixes.append("short_digits")
        value = value.zfill(8)
    if not value:
        return None, "empty"
    if not CANONICAL_CN_RE.match(value):
        return value, "unrecognised"
    return value, "+".join(fixes) or "canonical"


def check_date(value: object, field: str, snapshot: date) -> str | None:
    """Return a problem label for a date field, or None if it looks fine."""
    if not isinstance(value, str):
        return f"not_string:{type(value).__name__}"
    if TIMESTAMP_RE.match(value):
        return "timestamp_not_date"
    if not DATE_RE.match(value):
        return "bad_format"
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return "invalid_calendar_date"
    if parsed > snapshot:
        return "after_snapshot_date"
    if field == "notified_on" and parsed < PSC_REGIME_START:
        return "before_psc_regime_2016_04_06"
    return None


def as_date(value: object) -> date | None:
    if isinstance(value, str) and len(value) >= 10:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


@dataclass
class CorporateLink:
    owned: str            # normalised company_number of the controlled company
    reg_raw: object       # registration_number exactly as given
    reg_norm: str | None  # normalised registration number
    uk_like: bool         # country_registered or place_registered looks like the UK
    country: object
    name: str
    line: int


class Profile:
    def __init__(self, snapshot: date, examples: int = 3):
        self.snapshot = snapshot
        self.examples = examples
        self.lines = 0
        self.malformed: list[tuple[int, str, str | None]] = []  # (line, error, kind if recoverable)
        self.structure = Counter()          # problems with top-level shape
        self.kinds = Counter()
        self.kinds_active = Counter()
        self.keysets: dict[str, Counter] = defaultdict(Counter)
        self.key_presence: dict[str, Counter] = defaultdict(Counter)
        self.cn_formats = Counter()
        self.cn_examples: dict[str, list] = defaultdict(list)
        self.cn_prefixes = Counter()
        self.self_link_mismatch = 0
        self.date_problems = Counter()
        self.date_examples: dict[tuple, list] = defaultdict(list)
        self.ceased_before_notified = 0
        self.missing_natures = Counter()
        self.dob_problems = Counter()
        self.seen_hash: dict[bytes, int] = {}
        self.exact_dups: list[tuple[int, int]] = []
        self.self_hash: dict[str, bytes] = {}
        self.conflicting_self: list[tuple[str, int]] = []
        self.unique_counts = Counter()
        self.trailer: dict | None = None
        self.trailer_line: int | None = None
        self.companies: set[str] = set()
        self.statements = Counter()
        self.corporate_links: list[CorporateLink] = []
        self.legal_person_active: dict[str, list[str]] = defaultdict(list)
        self.super_secure_active = Counter()
        self.individuals_active = Counter()
        self.individual_identity = Counter()
        self.country_values = Counter()

    # Per-line processing.
    def add_line(self, lineno: int, line: str) -> None:
        self.lines = lineno
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            m = KIND_IN_RAW_RE.search(line)
            self.malformed.append((lineno, f"{exc.msg} at char {exc.pos}", m.group(1) if m else None))
            return
        if not isinstance(rec, dict) or not isinstance(rec.get("data"), dict):
            self.structure["not_an_object_with_data"] += 1
            return
        data = rec["data"]
        kind = data.get("kind")
        if not isinstance(kind, str):
            self.structure["missing_kind"] += 1
            return

        if kind.startswith(TRAILER_PREFIX):
            self.trailer, self.trailer_line = data, lineno
            return

        # Duplicates: exact copies, and same self link with different content.
        digest = hashlib.blake2b(
            json.dumps(rec, sort_keys=True, separators=(",", ":")).encode(), digest_size=16
        ).digest()
        if digest in self.seen_hash:
            self.exact_dups.append((self.seen_hash[digest], lineno))
            return  # profile each distinct record once
        self.seen_hash[digest] = lineno
        self_link = (data.get("links") or {}).get("self")
        if self_link:
            if self_link in self.self_hash and self.self_hash[self_link] != digest:
                self.conflicting_self.append((self_link, lineno))
            self.self_hash.setdefault(self_link, digest)

        self.kinds[kind] += 1
        active = "ceased_on" not in data and not data.get("ceased")
        if active:
            self.kinds_active[kind] += 1
        self.keysets[kind][frozenset(data.keys())] += 1
        self.key_presence[kind].update(data.keys())
        if is_psc_kind(kind):
            self.unique_counts["psc"] += 1
        elif kind == STATEMENT_KIND:
            self.unique_counts["statements"] += 1
            self.statements[(data.get("statement"), active)] += 1
        elif kind == EXEMPTIONS_KIND:
            self.unique_counts["exemptions"] += 1

        # Company number.
        raw_cn = rec.get("company_number")
        cn, fmt = normalise_number(raw_cn)
        self.cn_formats[fmt] += 1
        if fmt != "canonical" and len(self.cn_examples[fmt]) < self.examples:
            self.cn_examples[fmt].append((lineno, raw_cn))
        if cn:
            self.companies.add(cn)
            if cn[:2].isalpha():
                self.cn_prefixes[cn[:2]] += 1
            m = re.match(r"/company/([^/]+)/", self_link or "")
            if m and normalise_number(m.group(1))[0] != cn:
                self.self_link_mismatch += 1

        # Dates.
        for field in ("notified_on", "ceased_on"):
            if field not in data:
                if field == "notified_on" and (is_psc_kind(kind) or kind == STATEMENT_KIND) \
                        and not kind.startswith("super-secure"):
                    self.date_problems[(field, "missing")] += 1
                continue
            problem = check_date(data[field], field, self.snapshot)
            if problem:
                self.date_problems[(field, problem)] += 1
                ex = self.date_examples[(field, problem)]
                if len(ex) < self.examples:
                    ex.append((lineno, cn, data[field]))
        n_on, c_on = as_date(data.get("notified_on")), as_date(data.get("ceased_on"))
        if n_on and c_on and c_on < n_on:
            self.ceased_before_notified += 1

        dob = data.get("date_of_birth")
        if is_individual_kind(kind):
            if not data.get("natures_of_control"):
                self.missing_natures[kind] += 1
            if not isinstance(dob, dict):
                self.dob_problems["missing"] += 1
            else:
                month, year = dob.get("month"), dob.get("year")
                if not (isinstance(month, int) and 1 <= month <= 12):
                    self.dob_problems["bad_month"] += 1
                if not (isinstance(year, int) and 1900 <= year <= self.snapshot.year):
                    self.dob_problems["bad_year"] += 1
                elif self.snapshot.year - year < 16:
                    self.dob_problems["younger_than_16"] += 1

        if not (cn and active):
            return
        # Things that only matter for active records.
        if is_individual_kind(kind):
            self.individuals_active[cn] += 1
            self.individual_identity[(data.get("name"), json.dumps(dob, sort_keys=True))] += 1
        elif kind.startswith("super-secure"):
            self.super_secure_active[cn] += 1
        elif kind.startswith("legal-person"):
            self.legal_person_active[cn].append(data.get("name") or "?")
        elif is_corporate_kind(kind):
            ident = data.get("identification") or {}
            country = ident.get("country_registered")
            place = ident.get("place_registered")
            self.country_values[country] += 1
            reg_raw = ident.get("registration_number")
            reg_norm, _ = normalise_number(reg_raw) if reg_raw else (None, "missing")
            uk_like = bool(UK_RE.search(f"{country or ''} {place or ''}"))
            self.corporate_links.append(
                CorporateLink(cn, reg_raw, reg_norm, uk_like, country, data.get("name") or "?", lineno)
            )

    # Analysis after streaming.
    def resolve_links(self):
        """Classify every active corporate PSC. Return the graph of followable edges."""
        outcome = Counter()
        examples: dict[str, list] = defaultdict(list)
        edges: dict[str, list[tuple[str, str]]] = defaultdict(list)    # owned -> [(owner, name)]
        unfollowable: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for link in self.corporate_links:
            if not link.reg_raw:
                reason = "no_registration_number"
            elif not link.uk_like:
                reason = ("non_uk_but_number_matches_a_company_in_file"
                          if link.reg_norm in self.companies else "non_uk_registration")
            elif not link.reg_norm or not CANONICAL_CN_RE.match(link.reg_norm):
                reason = "uk_but_unrecognised_number"
            elif link.reg_norm not in self.companies:
                reason = "uk_company_not_in_snapshot"
            elif link.reg_norm == link.owned:
                reason = "self_ownership"
            else:
                reason = "followed"
                edges[link.owned].append((link.reg_norm, link.name))
            outcome[reason] += 1
            if reason != "followed":
                unfollowable[link.owned].append((link.name, reason))
                if len(examples[reason]) < self.examples:
                    examples[reason].append((link.line, link.owned, link.name, link.reg_raw, link.country))
        return outcome, examples, edges, unfollowable

    @staticmethod
    def strongly_connected(edges) -> list[list[str]]:
        """Iterative Tarjan's algorithm. Return the components that contain a cycle (size > 1)."""
        index, low, on_stack, stack, out, counter = {}, {}, set(), [], [], 0
        nodes = set(edges) | {o for outs in edges.values() for o, _ in outs}
        for root in nodes:
            if root in index:
                continue
            work = [(root, iter([o for o, _ in edges.get(root, [])]))]
            index[root] = low[root] = counter; counter += 1
            stack.append(root); on_stack.add(root)
            while work:
                node, it = work[-1]
                advanced = False
                for nxt in it:
                    if nxt not in index:
                        index[nxt] = low[nxt] = counter; counter += 1
                        stack.append(nxt); on_stack.add(nxt)
                        work.append((nxt, iter([o for o, _ in edges.get(nxt, [])])))
                        advanced = True
                        break
                    if nxt in on_stack:
                        low[node] = min(low[node], index[nxt])
                if advanced:
                    continue
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == index[node]:
                    comp = []
                    while True:
                        w = stack.pop(); on_stack.discard(w); comp.append(w)
                        if w == node:
                            break
                    if len(comp) > 1:
                        out.append(comp)
        return out

    @staticmethod
    def bfs(start: str, edges) -> tuple[dict[int, list[tuple[str, str, str]]], int]:
        """Breadth-first walk up the ownership graph.

        Return ({level: [(company, reached_from, via_name)]}, number of edges skipped
        because they lead to a company already visited, i.e. a cycle or a second route).
        """
        levels = {0: [(start, "", "")]}
        seen, frontier, skipped, level = {start}, [start], 0, 0
        while frontier:
            level += 1
            nxt = []
            for company in frontier:
                for owner, name in edges.get(company, []):
                    if owner in seen:
                        skipped += 1
                        continue
                    seen.add(owner)
                    nxt.append(owner)
                    levels.setdefault(level, []).append((owner, company, name))
            frontier = nxt
        return levels, skipped


# Rendering the report.
def md_table(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c).replace("|", "\\|") for c in row) + " |" for row in rows]
    return "\n".join(out)


def render(p: Profile, n_traces: int) -> str:
    out = []
    w = out.append
    distinct = len(p.seen_hash)
    w(f"Snapshot date: **{p.snapshot}**. Lines read: **{p.lines:,}**. "
      f"Distinct records: **{distinct:,}**. Companies (normalised): **{len(p.companies):,}**.\n")

    w("### 1. Parsing and structure\n")
    w(f"- Malformed JSON lines: **{len(p.malformed)}**")
    for line, err, kind in p.malformed:
        w(f"  - line {line}: {err}; kind recoverable from raw text: `{kind}`")
    for k, v in p.structure.items():
        w(f"- {k}: {v}")
    if p.trailer:
        w(f"- Trailer (`{p.trailer.get('kind')}`) at line {p.trailer_line} of {p.lines} "
          f"({'last line' if p.trailer_line == p.lines else 'NOT the last line'})")
    else:
        w("- **No trailer found**")
    w("")

    w("### 2. Kinds (distinct records)\n")
    w(md_table(["kind", "records", "active", "ceased"],
               [(k, f"{v:,}", f"{p.kinds_active[k]:,}", f"{v - p.kinds_active[k]:,}")
                for k, v in p.kinds.most_common()]))
    w("")

    w("### 3. Key sets per kind\n")
    w("'Always' means present in every record of that kind. Optional keys show how often they appear.\n")
    rows = []
    for kind, total in p.kinds.most_common():
        pres = p.key_presence[kind]
        always = sorted(k for k, c in pres.items() if c == total)
        optional = sorted(((k, c) for k, c in pres.items() if c < total), key=lambda x: -x[1])
        rows.append((kind, len(p.keysets[kind]), ", ".join(always),
                     ", ".join(f"{k} ({c / total:.0%})" for k, c in optional) or "none"))
    w(md_table(["kind", "distinct key sets", "always", "optional (share)"], rows))
    w("")

    w("### 4. Company-number formats (`company_number`)\n")
    w(md_table(["format", "records", "examples (line: raw value)"],
               [(f, f"{c:,}", "; ".join(f"{ln}: `{v!r}`" for ln, v in p.cn_examples.get(f, [])))
                for f, c in p.cn_formats.most_common()]))
    w(f"\n- Letter prefixes: {', '.join(f'{k} {v}' for k, v in p.cn_prefixes.most_common())}")
    w(f"- Records whose self-link company differs from `company_number` after normalising: "
      f"{p.self_link_mismatch}\n")

    w("### 5. Dates and other field problems\n")
    w(md_table(["field", "problem", "records", "examples (line, company, value)"],
               [(f, prob, c, "; ".join(f"{ln}, {cn}, `{v}`" for ln, cn, v in p.date_examples.get((f, prob), [])))
                for (f, prob), c in p.date_problems.most_common()]))
    w(f"\n- `ceased_on` earlier than `notified_on`: **{p.ceased_before_notified}**")
    w(f"- Individuals with no `natures_of_control`: {dict(p.missing_natures)}")
    w(f"- Individual date-of-birth problems: {dict(p.dob_problems) or 'none'}\n")

    w("### 6. Duplicates\n")
    w(f"- Exact duplicate records (identical JSON): **{len(p.exact_dups)}**. "
      f"Examples (first line, duplicate line): {p.exact_dups[:p.examples]}")
    w(f"- Same `links.self`, different content: **{len(p.conflicting_self)}** {p.conflicting_self[:p.examples]}")
    multi = sum(1 for v in p.individual_identity.values() if v > 1)
    w(f"- Active individuals whose (name, date of birth) appears in more than one record: "
      f"{multi:,} identities. This is the person-identity question for de-duplication.\n")

    w("### 7. Trailer reconciliation\n")
    if p.trailer:
        rows = []
        for label, key in (("psc", "persons_of_significant_control_count"),
                           ("statements", "statements_count"), ("exemptions", "exemptions_count")):
            expected = p.trailer.get(key)
            got = p.unique_counts[label]
            rows.append((label, expected, got, (expected or 0) - got))
        w(md_table(["category", "trailer says", "distinct records parsed", "difference"], rows))
        w(f"\nMalformed lines that couldn't be counted: {len(p.malformed)}. "
          f"Trailer `generated_at`: {p.trailer.get('generated_at')}\n")

    w("### 8. Statements (active and ceased)\n")
    w(md_table(["statement", "active", "records"],
               [(s, a, c) for (s, a), c in sorted(p.statements.items(), key=lambda x: -x[1])]))
    w("")

    outcome, examples, edges, unfollowable = p.resolve_links()
    w("### 9. Resolving active corporate PSCs to companies\n")
    w(md_table(["outcome", "links", "examples (line, owned, name, raw reg, country)"],
               [(o, c, "; ".join(f"{e[0]}, {e[1]}, {e[2]}, `{e[3]!r}`, {e[4]}" for e in examples.get(o, [])))
                for o, c in outcome.most_common()]))
    w("\n`country_registered` values on active corporate PSCs (top 20):\n")
    w(", ".join(f"`{k}` {v}" for k, v in p.country_values.most_common(20)))
    legal = sum(len(v) for v in p.legal_person_active.values())
    w(f"\n- Active legal-person PSCs (terminal, nothing to follow): {legal}")
    w(f"- Active super-secure PSCs (identity protected): {sum(p.super_secure_active.values())}\n")

    w("### 10. Ownership graph (followed edges only)\n")
    sccs = p.strongly_connected(edges)
    n_edges = sum(len(v) for v in edges.values())
    w(f"- Companies with at least one followed corporate owner: {len(edges):,}. Edges: {n_edges:,}")
    w(f"- Ownership cycles (strongly connected groups larger than 1): **{len(sccs)}**, "
      f"covering {sum(map(len, sccs))} companies. Sizes: {sorted(Counter(map(len, sccs)).items())}")
    depth, reach, skipped_any = {}, {}, {}
    for company in p.companies:
        levels, skipped = p.bfs(company, edges)
        depth[company] = max(levels)
        reach[company] = sum(len(v) for lvl, v in levels.items() if lvl > 0)
        skipped_any[company] = skipped
    dist = Counter(depth.values())
    w(f"- Deepest level reached by BFS (highest controlling company level) per company: "
      f"{', '.join(f'L{k}: {v:,}' for k, v in sorted(dist.items()))}")
    w(f"- Largest number of companies above one company: {max(reach.values())}")
    w(f"- Companies whose BFS hit an already visited company (a cycle or a second route to the same owner): "
      f"{sum(1 for v in skipped_any.values() if v):,}\n")

    w("### 11. Traced chains (BFS from a starting company)\n")
    picks = []
    picks += sorted(depth, key=lambda c: (-depth[c], c))[:1]                         # deepest
    picks += sorted(reach, key=lambda c: (-reach[c], c))[:1]                         # widest
    if sccs:
        picks.append(sorted(sccs, key=len)[0][0])                                    # in a cycle
    picks += [c for c in sorted(unfollowable) if c in edges][:1]                     # partly unfollowable
    seen_pick = []
    for c in picks:
        if c not in seen_pick:
            seen_pick.append(c)
    for start in seen_pick[:max(n_traces, 1)]:
        levels, skipped = p.bfs(start, edges)
        w(f"**Start: {start}** (levels 0 to {max(levels)}, {skipped} edges skipped as already visited)\n")
        w("```")
        for lvl in sorted(levels):
            for company, came_from, via in levels[lvl]:
                ind = p.individuals_active.get(company, 0)
                extra = [f"{ind} individual(s)"]
                if p.super_secure_active.get(company):
                    extra.append(f"{p.super_secure_active[company]} super-secure")
                if company in p.legal_person_active:
                    extra.append(f"legal person(s): {', '.join(p.legal_person_active[company])}")
                for name, reason in unfollowable.get(company, []):
                    extra.append(f"cannot follow '{name}' ({reason})")
                arrow = f"  <- owns {came_from} as '{via}'" if came_from else ""
                w(f"L{lvl}  {company}{arrow}  [{'; '.join(extra)}]")
        w("```\n")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--out", help="write the Markdown report here instead of to stdout")
    ap.add_argument("--trace", type=int, default=4, help="number of chains to trace")
    ap.add_argument("--snapshot-date", help="YYYY-MM-DD; default: taken from the file name")
    args = ap.parse_args(argv)

    if args.snapshot_date:
        snapshot = date.fromisoformat(args.snapshot_date)
    else:
        m = SNAPSHOT_IN_NAME_RE.search(args.path)
        if not m:
            ap.error("cannot infer the snapshot date from the file name; pass --snapshot-date")
        snapshot = date.fromisoformat(m.group(1))

    profile = Profile(snapshot)
    with gzip.open(args.path, "rt", encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, start=1):
            profile.add_line(lineno, line)

    report = render(profile, args.trace)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report + "\n")
    else:
        sys.stdout.write(report + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
