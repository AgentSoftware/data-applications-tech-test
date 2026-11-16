# 0004: Super-secure PSCs are always shown as protected placeholders

- Status: Accepted (2026-11-13)
- Related: spec 00 D1, Q5

## Context

Super-secure PSCs are people whose identity Companies House withholds for their protection. There are 37 records in the sample, 33 of them active. Their records contain only `kind`, `description`, `ceased`, `etag` and `links`, with no name, date of birth or address.

The user suggested an optional parameter that protects them by default but can reveal them.

## Options

1. Leave them out of the response.
2. Show a placeholder, with an option to reveal the details.
3. Always show a placeholder.

## Decision

Option 3. Each one appears in the level's `protected` list as `{"kind", "description", "via"}`.
- A reveal option can't reveal anything, because the source data never contains the identity.
- Leaving them out would make the answer look complete when someone is actually there.

## Consequences

- Customers can tell "someone protected controls this" apart from "nobody".
- If the data ever did carry protected details, the right control would be access control (a separate grant), not a request parameter.
- Legal persons get the same visible treatment, in `other_controllers`. Corporate PSCs we can't follow are listed in `unfollowed` with a reason code (see [0007](0007-what-counts-as-a-person.md) and [0009](0009-following-links-and-chain-breaks.md)).
