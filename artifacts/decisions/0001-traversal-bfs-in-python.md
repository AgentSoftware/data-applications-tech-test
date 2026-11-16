# 0001: Compute ownership levels with BFS in Python

- Status: Accepted (2026-11-13)
- Related: spec 00 D5, D11; spec 01 section 10

## Context

The endpoint returns people grouped by control level: level 0 is the company itself, and level N is N corporate hops up. The profile found the ownership data is a graph, not simple chains:
- 42 cycles covering 118 companies (the largest has 14 companies);
- 19 companies that own themselves;
- 879 companies that reach the same owner by more than one route;
- chains up to 22 levels deep.

Levels must be precomputed, because the API does one lookup and no traversal.

## Options

1. **BFS in Python** over an in-memory map from each company to its followed owners.
2. **Recursive CTE in Postgres** over a link table.
3. **DuckDB** recursive SQL, then load the result into Postgres.

## Decision

Option 1.
- **Levels:** BFS visits companies in order of distance, so the first time it reaches a company is its lowest level. That is the "most direct control" rule in [0003](0003-multiple-routes-lowest-level-default.md).
- **Cycles:** each traversal keeps a visited set for its starting company, so a cycle or self-link is visited only once. A cycle is logged to `data_issue` once per cycle (the strongly connected component found by Tarjan's algorithm), not once per company, so the log stays readable.
- **Depth cap:** a cap of 50 is a safety net. If it's ever hit, it logs an issue. The observed maximum is 22.
- **Input:** the BFS runs over a prebuilt map of `owned company -> [owner companies]`, built once from the cleaned links. It never reads the raw records.

## Consequences

- Traversal is a pure function, so it's easy to unit-test with small cases: a cycle, a self-link, a diamond-shaped group and a broken link.
- Recursive CTEs need explicit cycle columns (`CYCLE ... SET`). They're harder to test and harder to read, which is why option 2 was not chosen.
- Running one BFS per company repeats work across large groups. That's fine for the sample (about 7.9k links). For the full snapshot (about 16M records and about 3M links) the link map still fits in memory, but the production write-up should cover memoising shared ancestors, or a distributed job (Dataflow or BigQuery).
