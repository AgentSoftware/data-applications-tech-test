"""Copy every raw line for the given companies from the snapshot into a test fixture.

The source file is only read. A totals line with counts for the copied records and the source's
generated_at is appended, so the fixture reconciles and has a snapshot date. That line is synthetic.

Usage: python scripts/extract_fixture.py <snapshot.txt.gz> <out.jsonl> <company_number>...
"""
import gzip
import json
import sys

src, dst, wanted = sys.argv[1], sys.argv[2], set(sys.argv[3:])
counts = {"persons_of_significant_control_count": 0, "statements_count": 0, "exemptions_count": 0}
generated_at, kept = None, []
with gzip.open(src, "rb") as f:
    for raw in f:
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        kind = rec.get("data", {}).get("kind", "")
        if kind.startswith("totals#"):
            generated_at = rec["data"].get("generated_at")
            continue
        cn = str(rec.get("company_number") or "").strip().upper()
        cn = cn.zfill(8) if cn.isdigit() else cn
        if cn in wanted:
            kept.append(raw.rstrip(b"\r\n"))
            key = {"persons-with-significant-control-statement": "statements_count",
                   "exemptions": "exemptions_count"}.get(kind, "persons_of_significant_control_count")
            counts[key] += 1
trailer = {"data": {"kind": "totals#persons-of-significant-control-snapshot", **counts, "generated_at": generated_at}}
with open(dst, "wb") as f:
    f.write(b"\n".join(kept + [json.dumps(trailer).encode()]) + b"\n")
print(f"{dst}: {len(kept)} records for {len(wanted)} companies")
