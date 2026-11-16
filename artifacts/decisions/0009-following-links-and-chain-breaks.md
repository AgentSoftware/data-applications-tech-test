# 0009: Following corporate links, and what happens when a chain breaks

- Status: Accepted (2026-11-13). Revised the same day after an external review: added the `R` format and missing jurisdictions, and checked prefix padding against the data.
- Related: spec 00 D3, D4, D13, D14; spec 01 section 9; [0005](0005-reason-codes-in-data-http-codes-in-api.md), [0007](0007-what-counts-as-a-person.md)

## Context

The only link between a corporate PSC and its company is `identification.registration_number`, plus `country_registered` and `place_registered`. Active corporate links in the sample, as the profile classified them with the earlier rule, which padded digits only:

| outcome | count |
|---|---|
| followed | 7,861 |
| non-UK registration | 358 |
| no registration number | 239 |
| UK, but company not in the snapshot | 123 |
| foreign number that matches a UK company after padding (for example Goldman Sachs, Delaware 2923466) | 41 |
| UK, but not in a format that rule recognised (`Sc19230`, `Zc202`, `Sl32751` …) | 32 |
| self-ownership | 19 |

**Prefix padding, checked against the data:**
- The review suggested that padding a prefixed number with fewer than six digits, such as `Sc19230` to `SC019230`, is a guess.
- In the data, 13 active UK links have that form. When padded, **12 of the 13 match a company in the sample**, for example `SC034970` (John Menzies), `NI043691` and `SC002042` (J. & P. Coats).
- The sample deliberately includes the companies that own others (`data/README.md`). So this is the same "dropped leading zeros" mistake as the all-digit numbers, not a guess. The one miss, `SC019230`, stops as `uk_company_not_in_snapshot`.

**Missing jurisdiction:** 241 active corporate PSCs have no `place_registered`. All of them also have no `country_registered`, and **none** of them has a valid UK number that's in the snapshot.

## Options

1. Join on the padded number whatever the country.
2. Follow only UK registrations, after normalising the number. Every other link stops the chain with a reason.
3. Option 2, plus fuzzy name matching for links that fail.

## Decision

Option 2.
- **UK test:** `country_registered` or `place_registered` normalises to England, Wales, Scotland, Northern Ireland, the UK, Great Britain or Companies House.
- **Number normalisation:** one shared function, also used for `company_number` (ADR 0005):
  1. Trim, upper-case and remove inner spaces.
  2. All digits: zero-pad to 8 characters.
  3. Two letters followed by 1 to 6 digits: zero-pad the digits to 6 characters.
  4. Accepted patterns: `^\d{8}$`, `^[A-Z]{2}\d{6}$` and `^R\d{7}$`. The last is the old Northern Ireland register; `R0000134` is a real company number in the file.
  5. Anything else is `unrecognised_registration_number`.
- **Missing jurisdiction** (no country and no place): not followed, logged as `jurisdiction_missing`. We don't guess the country from the number's format. The data shows that this loses no links in the sample.
- **Natures of control:** we follow every active corporate PSC, whatever its natures of control.
- **Corporate beneficial owners:** handled the same way as corporate PSCs.
- **When a chain breaks:**
  - The chain stops at that link.
  - The controller is listed in its level's `unfollowed` list with a reason code.
  - The levels below it are still returned.
  - A `data_issue` row is written with action `not_followed`.
  - Legal persons aren't chain breaks (ADR 0007).
- **Reason codes:** `non_uk_registration`, `foreign_number_collision`, `no_registration_number`, `jurisdiction_missing`, `unrecognised_registration_number`, `uk_company_not_in_snapshot` and `self_ownership`. Cycles are covered in ADR 0001.

## Consequences

- The 41 foreign numbers are never linked to the wrong UK company.
- Fuzzy matching was rejected: a wrong link would put the wrong people in an answer, which is worse than an honest "couldn't follow".
- Prefix padding recovers about 12 real links in the sample. It's tested against those cases.
- `uk_company_not_in_snapshot` is expected in the sample, because it's a subset. In the full snapshot it should be rare, and worth monitoring (ADR 0012).
