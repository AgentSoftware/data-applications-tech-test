"""Corporate links, BFS levels and cycles. Rules: spec 02 sections 3.2, 3.3 and 4; ADRs 0001, 0003 and 0009."""
from .normalise import is_uk, normalise_number
from .parse import Issue

MAX_LEVEL = 50


def classify_links(psc_rows, companies: set, issues: list) -> list[dict]:
    """One ownership_link row per active corporate PSC. Sets row['registration_number'] on the PSC rows."""
    links = []
    for row in psc_rows:
        if row["psc_type"] != "corporate" or not row["is_active"]:
            continue
        n, owned, raw = row["source_line"], row["company_number"], row["registration_number_raw"]
        reg = normalise_number(raw)
        row["registration_number"] = reg
        uk = is_uk(row["country_registered"], row["place_registered"])
        if not (isinstance(raw, str) and raw.strip()):
            status = "no_registration_number"
        elif uk is None:
            status = "jurisdiction_missing"
        elif not uk:
            status = "foreign_number_collision" if reg in companies else "non_uk_registration"
        elif reg is None:
            status = "unrecognised_registration_number"
        elif reg == owned:
            status = "self_ownership"
        elif reg not in companies:
            status = "uk_company_not_in_snapshot"
        else:
            status = "followed"
        if uk and reg and reg != raw:
            issues.append(Issue("registration_number_normalised", "info", "fixed", n, owned,
                                "registration_number", raw, reg))
        if status != "followed":
            issues.append(Issue(status, "warning", "not_followed", n, owned, "registration_number", raw,
                                details={"country_registered": row["country_registered"],
                                         "place_registered": row["place_registered"]}))
        links.append({"source_line": n, "owned_company_number": owned,
                      "owner_company_number": reg if status == "followed" else None, "link_status": status})
    return links


def owner_map(links) -> dict[str, list[str]]:
    """owned company -> distinct owner companies, in source_line order."""
    owners = {}
    for link in sorted(links, key=lambda l: l["source_line"]):
        if link["link_status"] == "followed":
            lst = owners.setdefault(link["owned_company_number"], [])
            if link["owner_company_number"] not in lst:
                lst.append(link["owner_company_number"])
    return owners


def bfs(start: str, owners: dict, max_level: int = MAX_LEVEL):
    """Returns ({company: (level, via, route_count)}, cap_hit). via excludes start; route_count = shortest routes."""
    seen = {start: (0, (), 1)}
    frontier, level = [start], 0
    while frontier and level < max_level:
        nxt = []
        for company in frontier:
            _, via, count = seen[company]
            for owner in owners.get(company, ()):
                if owner not in seen:
                    seen[owner] = (level + 1, via + (owner,), count)
                    nxt.append(owner)
                elif seen[owner][0] == level + 1:  # another shortest route
                    lvl, v, c = seen[owner]
                    seen[owner] = (lvl, v, c + count)
        frontier, level = nxt, level + 1
    cap_hit = bool(frontier) and any(o not in seen for c in frontier for o in owners.get(c, ()))
    return seen, cap_hit


def find_cycles(owners: dict) -> list[list[str]]:
    """Strongly connected groups of more than one company (iterative Tarjan)."""
    index, low, on_stack, stack, groups, counter = {}, {}, set(), [], [], 0
    for root in owners:
        if root in index:
            continue
        work = [(root, iter(owners.get(root, ())))]
        index[root] = low[root] = counter; counter += 1
        stack.append(root); on_stack.add(root)
        while work:
            node, it = work[-1]
            child = next(it, None)
            if child is not None:
                if child not in index:
                    index[child] = low[child] = counter; counter += 1
                    stack.append(child); on_stack.add(child)
                    work.append((child, iter(owners.get(child, ()))))
                elif child in on_stack:
                    low[node] = min(low[node], index[child])
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index[node]:
                group = []
                while True:
                    c = stack.pop(); on_stack.discard(c); group.append(c)
                    if c == node:
                        break
                if len(group) > 1:
                    groups.append(sorted(group))
    return sorted(groups)


def build_ancestors(companies, owners: dict, issues: list) -> list[dict]:
    """company_ancestor rows for every company (itself at level 0), plus cycle and depth-cap issues."""
    for group in find_cycles(owners):
        issues.append(Issue("cycle", "warning", "flagged", company_number=group[0], details={"companies": group}))
    rows = []
    for start in sorted(companies):
        seen, cap_hit = bfs(start, owners)
        if cap_hit:
            issues.append(Issue("depth_cap_reached", "warning", "flagged", company_number=start,
                                details={"max_level": MAX_LEVEL}))
        rows += [{"company_number": start, "ancestor_company_number": c, "level": lvl,
                  "via_company_numbers": list(via), "route_count": count}
                 for c, (lvl, via, count) in seen.items()]
    return rows
