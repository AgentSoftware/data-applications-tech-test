from pathlib import Path

import pytest

from psc_pipeline.graph import bfs, build_ancestors, classify_links, find_cycles, owner_map
from psc_pipeline.parse import parse_file

FIXTURES = Path(__file__).parent / "fixtures"


def corp(owned, reg, country="England", place=None, line=1, active=True):
    return {"source_line": line, "company_number": owned, "psc_type": "corporate", "is_active": active,
            "registration_number_raw": reg, "country_registered": country, "place_registered": place}


def load(name):
    out = parse_file(FIXTURES / name)
    companies = {r["company_number"] for r in out.psc + out.statements + out.exemptions}
    links = classify_links(out.psc, companies, out.issues)
    return out, companies, links


@pytest.mark.parametrize("row, status", [
    (corp("00000001", "00000002"), "followed"),
    (corp("00000001", "2"), "followed"),                                   # padded
    (corp("00000001", None), "no_registration_number"),
    (corp("00000001", "  "), "no_registration_number"),
    (corp("00000001", "00000002", country=None), "jurisdiction_missing"),
    (corp("00000001", "4801182", country="Delaware"), "non_uk_registration"),
    (corp("00000001", "2", country="Delaware"), "foreign_number_collision"),  # pads to a real company
    (corp("00000001", "Zc", country="United Kingdom"), "unrecognised_registration_number"),
    (corp("00000001", "1"), "self_ownership"),
    (corp("00000001", "00000099"), "uk_company_not_in_snapshot"),
])
def test_classify_link(row, status):
    issues = []
    [link] = classify_links([row], {"00000001", "00000002"}, issues)
    assert link["link_status"] == status
    assert link["owner_company_number"] == ("00000002" if status == "followed" else None)
    not_followed = [i for i in issues if i.action == "not_followed"]
    assert [i.check_code for i in not_followed] == ([] if status == "followed" else [status])


def test_ceased_and_non_corporate_rows_are_ignored():
    rows = [corp("00000001", "00000002", active=False), {**corp("00000001", "x"), "psc_type": "individual"}]
    issues = []
    assert classify_links(rows, {"00000001", "00000002"}, issues) == [] and issues == []


def test_registration_normalised_is_logged_only_for_uk():
    issues = []
    classify_links([corp("00000001", "2", line=1), corp("00000001", "2", country="Delaware", line=2)],
                   {"00000001", "00000002"}, issues)
    fixes = [i for i in issues if i.check_code == "registration_number_normalised"]
    assert [(i.source_line, i.raw_value, i.fixed_value) for i in fixes] == [(1, "2", "00000002")]


def test_zz_example():
    out, companies, links = load("zz_example.jsonl")
    assert [(l["source_line"], l["link_status"]) for l in links] == [
        (2, "followed"), (5, "followed"), (7, "non_uk_registration")]
    assert sorted(i.check_code for i in out.issues) == [
        "duplicate_record", "non_uk_registration", "registration_number_normalised"]
    seen, cap = bfs("ZZ000001", owner_map(links))
    assert seen == {"ZZ000001": (0, (), 1), "ZZ000002": (1, ("ZZ000002",), 1),
                    "ZZ000003": (2, ("ZZ000002", "ZZ000003"), 1)} and not cap


def test_diamond_counts_shortest_routes():
    # A owned by B and C; both owned by D; D owned by E. Two registrations of B -> D count once.
    owners = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": ["E"]}
    seen, _ = bfs("A", owners)
    assert seen["D"] == (2, ("B", "D"), 2) and seen["E"] == (3, ("B", "D", "E"), 2)
    links = [{"source_line": i, "owned_company_number": "B", "owner_company_number": "D", "link_status": "followed"}
             for i in (1, 2)]
    assert owner_map(links) == {"B": ["D"]}


def test_longer_route_is_not_counted():
    seen, _ = bfs("A", {"A": ["B", "C"], "B": ["C"]})
    assert seen["C"] == (1, ("C",), 1)


def test_depth_cap():
    chain = {str(i): [str(i + 1)] for i in range(5)}  # 0 -> 1 -> ... -> 5
    seen, cap = bfs("0", chain, max_level=3)
    assert max(l for l, _, _ in seen.values()) == 3 and cap
    seen, cap = bfs("0", chain, max_level=5)
    assert len(seen) == 6 and not cap


def test_real_cycle():
    out, companies, links = load("real_cycle.jsonl")
    owners = owner_map(links)
    assert owners == {"05104525": ["09090984"], "09090984": ["05104525"], "02889173": ["09090984"]}
    assert find_cycles(owners) == [["05104525", "09090984"]]
    seen, cap = bfs("02889173", owners)
    assert {c: lvl for c, (lvl, _, _) in seen.items()} == {"02889173": 0, "09090984": 1, "05104525": 2}
    issues = []
    rows = build_ancestors(companies, owners, issues)
    assert [i.check_code for i in issues] == ["cycle"]  # once per cycle, not once per company
    assert issues[0].details == {"companies": ["05104525", "09090984"]}
    assert len(rows) == 3 + 2 + 2


def test_self_loop_is_not_a_cycle():
    assert find_cycles({"A": ["A"]}) == [] and bfs("A", {"A": ["A"]})[0] == {"A": (0, (), 1)}


def test_bigger_cycle_and_two_groups():
    owners = {"A": ["B"], "B": ["C"], "C": ["A", "D"], "D": ["E"], "E": ["D"], "F": ["A"]}
    assert find_cycles(owners) == [["A", "B", "C"], ["D", "E"]]


def test_real_deep_chain():
    out, companies, links = load("real_deep_chain.jsonl")
    seen, cap = bfs("04555610", owner_map(links))
    level, via, count = seen["10003599"]
    assert level == 22 and len(via) == 22 and via[0] == "04555609" and count == 1 and not cap
    assert max(l for l, _, _ in seen.values()) == 22
    ceased = {r["source_line"] for r in out.psc if not r["is_active"]}
    assert not ceased & {l["source_line"] for l in links}  # ceased links never classified
