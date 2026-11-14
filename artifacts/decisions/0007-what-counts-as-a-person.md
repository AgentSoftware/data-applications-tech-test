# 0007: What counts as a person

- Status: Accepted (2026-11-13). Revised the same day: legal persons moved out of `unfollowed`.
- Related: spec 00 D1, D14; [0004](0004-super-secure-as-protected-placeholders.md), [0009](0009-following-links-and-chain-breaks.md)

## Context

A company's PSC records come in several kinds. Not all of them are people, and not all of them can be followed up a chain:

| kind | what it is |
|---|---|
| individual-person-with-significant-control | a natural person |
| individual-beneficial-owner | a natural person (overseas-entity register) |
| super-secure-person-with-significant-control | a natural person whose identity is withheld (33 active) |
| corporate-entity-person-with-significant-control | a company, which may be followable (about 8.7k active) |
| corporate-entity-beneficial-owner | a company (overseas-entity register) |
| legal-person-person-with-significant-control | a government, a corporation sole and so on, fully identified, with no company register behind it (64 active) |

## Options

1. People are individuals only. Everything else is dropped from the answer.
2. People are individuals. Every other controller still appears, in a list that says what it is.
3. Every controller counts as a "person".

## Decision

Option 2. Each level has up to five lists:
- **`people`:** individual PSCs and individual beneficial owners.
- **`protected`:** super-secure PSCs (ADR 0004).
- **`companies`:** the corporate PSCs and corporate beneficial owners we followed. Their people form the next level up.
- **`other_controllers`:** legal persons. A legal person is a real, identified controller at the top of its chain, **not** a failed link, so it gets no reason code and no `data_issue` row.
- **`unfollowed`:** the corporate PSCs we couldn't follow, each with a reason code (ADR 0009).

## Consequences

- An answer never shows "nobody" when the truth is "someone we can't name or follow".
- `unfollowed` means only "the pipeline couldn't follow this link". It is never used for a valid end of a chain.
- Customers who want only named people read just `people`.
