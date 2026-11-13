# 0003: Companies reached by several routes: list registrations at the lowest level, with no merging of people

- Status: Accepted (2026-11-13). Revised the same day after an external review.
- Related: spec 00 D6, Q4; [0001](0001-traversal-bfs-in-python.md)

## Revision history

- **v1** (user's suggestion):
  - Each *person* appeared once at their lowest level, matched by name plus date of birth.
  - `route_count` and `other_levels` were added to each person.
  - Every route was stored in a separate `psc_routes_by_company` table, capped at 50 per person, for an `all_routes=true` option.
- **v2** (this version):
  - Merging people and storing every route were both removed.
  - Why: a review (another agent, checked against the data) showed that v1 put a guess into the core answer, and that enumerating routes can blow up. The user agreed.
  - The full-routes option moves to `NOTES.md`, under "what I'd do next".

## Context

The same company can be reached by more than one route.

**Example:** A is owned by both B and C, and both are owned by D. In the profile, 879 companies reach the same owner by more than one route.

Separately, the same *person* can be registered against more than one company in a chain. For example, Jane is registered against A and also against D. The data has no stable ID for a person.

## Options

1. **Merge people** by name plus date of birth, and show each person once (v1).
2. **List each registration** at its company's lowest level, without merging.
3. **Store every route** (v1's extra table).

## Decision

Option 2.
- **A level means what the brief says:** "the people registered against" the companies at that level. Each active registration (one `psc` row) appears once, at its company's lowest level, as found by BFS.
  - If Jane is registered against A (level 0) and against D (level 2), she appears at both levels, as two registrations. That's literally true.
- **`via`:** the shortest route up to the company the registration belongs to. If several routes are equally short, the first one BFS finds is used, in a fixed order.
- **`route_count`:** the number of *shortest* routes to that company. BFS counts these for free, by adding up the counts of each company's parents on the level below. It tells the customer "this control reaches you more than one way".
- **No `other_levels`, no merging of people, no routes table.**

## Consequences

- The answer contains only facts from the register, with no guessed identity.
- A customer may see the same name at two levels. Each entry has its own `via`, so it's clear why.
- One BFS works out the level, `via` and `route_count`. There's no DFS and no risk of the search blowing up.
- This removes a table, the identity rule and the route cap from the data model.
- A future option: an "all routes" or "same person" annotation, described in `NOTES.md`.
