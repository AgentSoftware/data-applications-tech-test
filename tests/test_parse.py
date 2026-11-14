import gzip
import json
from datetime import date
from pathlib import Path

from psc_pipeline.parse import parse_file

FIXTURES = Path(__file__).parent / "fixtures"
TRAILER = {"data": {"kind": "totals#persons-of-significant-control-snapshot", "generated_at": "2026-10-29T07:08:01Z",
                    "persons_of_significant_control_count": 0, "statements_count": 0, "exemptions_count": 0}}


def ind(cn="00000001", **data):
    d = {"kind": "individual-person-with-significant-control", "name": "X", "notified_on": "2020-01-01",
         "date_of_birth": {"year": 1980, "month": 1}, "natures_of_control": ["voting-rights-25-to-50-percent"]}
    return {"company_number": cn, "data": d | data}


def run(tmp_path, *records, name="snap.txt", trailer=True):
    p = tmp_path / name
    lines = [r if isinstance(r, str) else json.dumps(r) for r in records]
    if trailer:
        lines.append(json.dumps(TRAILER))
    p.write_text("\n".join(lines) + "\n")
    return parse_file(p)


def codes(parsed):
    return sorted(i.check_code for i in parsed.issues)


def test_zz_example():
    out = parse_file(FIXTURES / "zz_example.jsonl")
    assert out.snapshot_date == date(2026, 10, 29)
    assert [r["source_line"] for r in out.psc] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert {r["name"]: r["is_active"] for r in out.psc if r["name"]} == {
        "Ada": True, "Two Ltd": True, "Bo": True, "Dan": False, "Three Ltd": True, "Cy": True, "Acme Inc": True}
    assert out.psc[7]["psc_type"] == "super_secure" and out.psc[7]["is_active"]
    assert codes(out) == ["duplicate_record"]  # Dan is ceased: valid history, no issue (ADR 0008)
    assert out.issues[0].source_line == 9 and out.issues[0].details == {"duplicate_of_line": 6}
    assert out.distinct_by_group["psc"] == 8 and out.trailer["persons_of_significant_control_count"] == 8


def test_pii_fields_are_not_kept():
    row = parse_file(FIXTURES / "zz_example.jsonl").psc[0]
    for dropped in ("address", "nationality", "country_of_residence", "name_elements", "etag"):
        assert dropped not in row


def test_gzip_input(tmp_path):
    p = tmp_path / "snap.txt.gz"
    with gzip.open(p, "wt") as f:
        f.write(json.dumps(ind()) + "\n" + json.dumps(TRAILER) + "\n")
    assert len(parse_file(p).psc) == 1


def test_malformed_lines_are_rejected_with_kind_recovered(tmp_path):
    out = run(tmp_path, ind(), '{"company_number":"1","data":{"kind":"individual-person-with-significant-control",',
              "", "[1, 2]", b"\xff\xfe".decode("latin-1"))
    assert codes(out) == ["malformed_json"] * 4
    assert out.malformed_by_group == {"psc": 1, "unknown": 3}
    assert len(out.psc) == 1


def test_trailer_is_not_data(tmp_path):
    out = run(tmp_path, ind())
    assert out.trailer is not None and out.distinct_by_group == {"psc": 1}


def test_snapshot_date_from_trailer_and_mismatch(tmp_path):
    out = run(tmp_path, ind(), name="snapshot-2026-10-22.txt")
    assert out.snapshot_date == date(2026, 10, 29)
    assert codes(out) == ["snapshot_date_mismatch"]


def test_no_snapshot_date_marks_nothing_active(tmp_path):
    out = run(tmp_path, ind(), trailer=False)  # no trailer and no date in the file name
    assert out.snapshot_date is None and out.psc[0]["is_active"] is False


def test_no_trailer_falls_back_to_file_name(tmp_path):
    out = run(tmp_path, ind(), name="snapshot-2026-10-22.txt", trailer=False)
    assert out.trailer is None and out.snapshot_date == date(2026, 10, 22)


def test_company_number_rules(tmp_path):
    out = run(tmp_path, ind(" 9906121"), ind(""), ind("ABC123"), {"data": ind()["data"]},
              {"company_number": "00000002", "data": {"kind": "something-new"}})
    assert codes(out) == ["company_number_normalised", "missing_company_number", "missing_company_number",
                          "unknown_kind", "unrecognised_company_number"]
    assert [r["company_number"] for r in out.psc] == ["09906121"]
    fix = next(i for i in out.issues if i.check_code == "company_number_normalised")
    assert (fix.raw_value, fix.fixed_value, fix.action) == (" 9906121", "09906121", "fixed")


def test_active_rule(tmp_path):
    out = run(tmp_path,
              ind(name="future-ceased", ceased_on="2027-01-01"),      # still active
              ind(name="future-notified", notified_on="2026-12-31"),  # not yet active
              ind(name="ceased-before-notified", notified_on="2021-01-01", ceased_on="2020-01-01"),
              ind(name="bad-ceased", ceased_on="2021-02-30"),
              ind(name="timestamp", ceased_on="2021-03-04T00:00:00Z"),
              ind(name="no-notified", notified_on=None))
    active = {r["name"]: r["is_active"] for r in out.psc}
    assert active == {"future-ceased": True, "future-notified": False, "ceased-before-notified": False,
                      "bad-ceased": False, "timestamp": False, "no-notified": False}
    assert codes(out) == ["ceased_before_notified", "date_timestamp_truncated", "invalid_date", "invalid_date",
                          "notified_after_snapshot"]
    assert out.psc[4]["ceased_on"] == date(2021, 3, 4) and out.psc[4]["ceased_on_raw"] == "2021-03-04T00:00:00Z"


def test_super_secure_uses_ceased_flag(tmp_path):
    ss = {"kind": "super-secure-person-with-significant-control", "description": "super-secure"}
    out = run(tmp_path, {"company_number": "00000001", "data": ss | {"ceased": False}},
              {"company_number": "00000001", "data": ss | {"ceased": True}})
    assert [r["is_active"] for r in out.psc] == [True, False]
    assert codes(out) == []  # no notified_on is fine for super-secure


def test_conflicting_duplicates_keep_the_ceased_copy(tmp_path):
    link = {"links": {"self": "/company/00000001/psc/individual/abc"}}
    out = run(tmp_path, ind(**link), ind(ceased_on="2022-01-01", **link))
    assert [r["source_line"] for r in out.psc] == [2]
    assert sorted((i.source_line, i.action) for i in out.issues) == [(1, "dropped"), (2, "flagged")]


def test_conflicting_duplicates_without_ceased_keep_the_first(tmp_path):
    link = {"links": {"self": "/company/00000001/psc/individual/abc"}}
    out = run(tmp_path, ind(name="A", **link), ind(name="B", **link))
    assert [r["name"] for r in out.psc] == ["A"]


def test_statements_and_exemptions(tmp_path):
    st = {"kind": "persons-with-significant-control-statement",
          "statement": "no-individual-or-entity-with-signficant-control", "notified_on": "2020-01-01"}
    out = run(tmp_path, {"company_number": "00000001", "data": st},
              {"company_number": "00000001", "data": st | {"ceased_on": "2021-01-01", "links": {"self": "s2"}}},
              {"company_number": "00000002", "data": {"kind": "exemptions", "exemptions": {"x": 1}}})
    assert [(r["statement_code"][:2], r["is_active"]) for r in out.statements] == [("no", True), ("no", False)]
    assert out.exemptions[0]["exemption_details"] == {"x": 1} and out.exemptions[0]["is_active"]
    assert out.distinct_by_group == {"statement": 2, "exemption": 1}


def test_person_checks(tmp_path):
    out = run(tmp_path, ind(date_of_birth={"year": 2011, "month": 1}),   # 15 on the snapshot date
              ind(date_of_birth={"year": 2010, "month": 10}),             # exactly 16 in October 2026
              ind(date_of_birth=None), ind(natures_of_control=[]),
              ind(date_of_birth={"year": 1980, "month": 13}), ind(date_of_birth="1980-01"),
              ind(date_of_birth=None, ceased_on="2021-01-01"))            # ceased: not checked
    assert codes(out) == ["implausible_birth_date", "missing_birth_date", "missing_birth_date",
                          "missing_birth_date", "missing_natures_of_control"]


def test_second_trailer_is_flagged(tmp_path):
    out = run(tmp_path, json.dumps(TRAILER), ind())
    assert codes(out) == ["duplicate_trailer"]


def test_every_line_is_accounted_for():
    """No record disappears silently: each line is the trailer, a row, or has an issue."""
    out = parse_file(FIXTURES / "zz_example.jsonl")
    rows = {r["source_line"] for r in out.psc + out.statements + out.exemptions}
    issued = {i.source_line for i in out.issues}
    assert rows | issued | {out.line_count} == set(range(1, out.line_count + 1))
