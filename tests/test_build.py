import json
from pathlib import Path

from psc_pipeline.build import build_payloads, control_status
from psc_pipeline.graph import build_ancestors, classify_links, owner_map
from psc_pipeline.parse import parse_file

FIXTURES = Path(__file__).parent / "fixtures"


def payloads_for(name):
    out = parse_file(FIXTURES / name)
    companies = {r["company_number"] for r in out.psc + out.statements + out.exemptions}
    links = classify_links(out.psc, companies, out.issues)
    ancestors = build_ancestors(companies, owner_map(links), out.issues)
    return build_payloads(out, links, ancestors, out.issues)


def test_zz_example_matches_hand_written_golden_file():
    payloads, statuses = payloads_for("zz_example.jsonl")
    expected = json.loads((FIXTURES / "zz_example_ZZ000001.json").read_text())
    assert payloads["ZZ000001"] == expected
    assert set(payloads) == {"ZZ000001", "ZZ000002", "ZZ000003"} and set(statuses.values()) == {"ok"}


def test_every_company_starts_at_its_own_level_0():
    payloads, _ = payloads_for("zz_example.jsonl")
    assert [p["levels"][0]["people"][0]["name"] for p in (payloads[c] for c in ("ZZ000002", "ZZ000003"))] == ["Bo", "Cy"]
    assert len(payloads["ZZ000003"]["levels"]) == 1  # Acme Inc is not followed: nothing above


def test_payload_is_json_serialisable():
    payloads, _ = payloads_for("real_deep_chain.jsonl")
    json.dumps(payloads)


def test_real_cycle_shows_loop_without_repeating():
    payloads, _ = payloads_for("real_cycle.jsonl")
    p = payloads["09090984"]
    assert [l["level"] for l in p["levels"]] == [0, 1]
    [c0] = p["levels"][0]["companies"]
    [c1] = p["levels"][1]["companies"]
    assert (c0["owner_company_number"], c0.get("already_at_level")) == ("05104525", None)
    assert (c1["owner_company_number"], c1["already_at_level"]) == ("09090984", 0)
    assert "people" not in p["levels"][0] and p["data_quality"]["check_codes"] == ["cycle"]
    q = payloads["02889173"]
    assert [l["companies"][0].get("already_at_level") for l in q["levels"]] == [None, None, 1]


def test_real_deep_chain_ends_with_statement():
    payloads, _ = payloads_for("real_deep_chain.jsonl")
    p = payloads["04555610"]
    assert len(p["levels"]) == 23 and p["control_status"] == "ok"
    top = p["levels"][22]
    assert top["statements"][0]["statement_code"] == "no-individual-or-entity-with-signficant-control"
    assert top["statements"][0]["company_number"] == "10003599" and len(top["statements"][0]["via"]) == 22
    assert payloads["10003599"]["control_status"] == "psc_statement_only"


def test_control_status_order():
    assert control_status({"people": [1], "statements": [1]}) == "ok"
    assert control_status({"exemptions": [1], "statements": [1]}) == "exempt"
    assert control_status({"statements": [1]}) == "psc_statement_only"
    assert control_status({}) == "no_active_psc"


def test_legal_person_goes_to_other_controllers(tmp_path):
    rec = {"company_number": "00000001", "data": {
        "kind": "legal-person-person-with-significant-control", "name": "The Secretary Of State",
        "identification": {"legal_form": "Government", "legal_authority": "UK"},
        "natures_of_control": ["ownership-of-shares-75-to-100-percent"], "notified_on": "2020-01-01"}}
    trailer = {"data": {"kind": "totals#x", "generated_at": "2026-10-29T00:00:00Z"}}
    (tmp_path / "s.txt").write_text(json.dumps(rec) + "\n" + json.dumps(trailer) + "\n")
    out = parse_file(tmp_path / "s.txt")
    links = classify_links(out.psc, {"00000001"}, out.issues)
    payloads, _ = build_payloads(out, links, build_ancestors({"00000001"}, owner_map(links), out.issues), out.issues)
    level0 = payloads["00000001"]["levels"][0]
    assert list(level0) == ["level", "other_controllers"]
    assert level0["other_controllers"][0]["legal_form"] == "Government" and "data_quality" not in payloads["00000001"]


def test_company_with_nothing_active_still_has_levels(tmp_path):
    rec = {"company_number": "00000001", "data": {"kind": "individual-person-with-significant-control",
           "name": "Gone", "notified_on": "2017-01-01", "ceased_on": "2018-01-01"}}
    trailer = {"data": {"kind": "totals#x", "generated_at": "2026-10-29T00:00:00Z"}}
    (tmp_path / "s.txt").write_text(json.dumps(rec) + "\n" + json.dumps(trailer) + "\n")
    out = parse_file(tmp_path / "s.txt")
    payloads, statuses = build_payloads(out, [], build_ancestors({"00000001"}, {}, out.issues), out.issues)
    assert payloads["00000001"]["levels"] == [] and statuses["00000001"] == "no_active_psc"
