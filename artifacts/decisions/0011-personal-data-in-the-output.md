# 0011: Personal data in the output (data minimisation)

- Status: Accepted (2026-11-13). Confirmed by the user; an external review recommended the same.
- Related: spec 00 D12, Q3; [0002](0002-storage-clean-tables-plus-serving-table.md)

## Context

Individual records carry:
- name and name elements;
- date of birth (month and year only; Companies House never publishes the day);
- nationality;
- country of residence;
- the full service address;
- identity-verification details (on 52% of records).

The customer question is "who is behind this company?". The customer must be able to tell apart two people with the same name. The pipeline doesn't merge people (ADR 0003), so it's the customer who needs the date of birth.

## Options

1. Pass through every field.
2. Keep the fields needed to identify the person and their control; drop the rest.
3. Name and natures of control only.

## Decision

Option 2.

| field | in the clean `psc` table | in the answer | why |
|---|---|---|---|
| name | yes | yes | core answer |
| date of birth (month and year) | yes | yes | the only way for a customer to tell same-name people apart; already public at this precision |
| natures of control, notified_on | yes | yes | what control they hold, and since when |
| kind | yes | yes | shows the record type |
| name elements | no | no | duplicates `name` |
| nationality, country of residence | no | no | not needed to answer the question |
| address | no | no | the most sensitive field, and not needed |
| identity verification details | no | no | about the verification process, not about control |
| etag, links | `links.self` only | no | used only for the duplicate rule |

Everything dropped stays in the raw file, so it can be added later without a re-design.

## Consequences

- The serving rows are smaller, and less personal data sits in the database.
- With option 3, two "John Smith"s would look like one person. That's why it was rejected.
- Month and year of birth appear in the answer.
