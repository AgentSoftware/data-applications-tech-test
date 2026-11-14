# 0013: Naming conventions for tables, columns and payload keys

- Status: Accepted (2026-11-14)
- Related: [plan 01](../plans/01-logical-data-model.md)

## Context

The user asked whether the names in the data model follow best practice. The v3 model had four problems:
- a column called `check`, which is a reserved word in SQL;
- generic `status` columns on three tables, each meaning something different;
- abbreviations such as `reg_number` and `dob_year`;
- a `company.status` column that would be confused with Companies House's own "company status" (active, dissolved).

## Options

1. Keep the v3 names.
2. Adopt a short, written convention and rename now, before any code exists. Renaming now costs nothing.

## Decision

Option 2. The convention:

| rule | example | why |
|---|---|---|
| lower `snake_case`, singular table names | `ownership_link`, not `OwnershipLinks` | Postgres folds unquoted names to lower case; singular reads as "one row is one…" |
| no reserved or overloaded words | `check` → `check_code` | `check` needs quoting everywhere |
| a domain prefix when a word is generic | `statement` → `psc_statement`, `exemption` → `psc_exemption` | "statement" also means a SQL statement |
| a qualified name for each status | `run_status`, `control_status`, `link_status` | each means a different thing; `control_status` avoids the clash with Companies House's company status |
| spell words out; keep only standard abbreviations | `registration_number`, `birth_year`; `psc` and `sha256` stay | readable without a glossary |
| one name for one thing in every table | `company_number`; role prefixes when one table has two (`owned_company_number`, `owner_company_number`) | joins are obvious |
| suffixes show the type or role | `is_` for booleans, `_on` for dates (as in the source), `_at` for timestamps, `_count` for counts, `_raw` for the original value next to a cleaned one | the meaning is visible from the name |
| arrays use plural names | `via_company_numbers` | |
| schemas by purpose | `psc` (published), `psc_staging` (being built), `psc_audit` (run history and issues) | |

**Payload JSON keys** use the same snake_case names as the columns. There's one exception: `via` stays short, because it appears on every entry and is defined once in the spec.

## Consequences

- The names are fixed before any code is written, so no migration is needed.
- `psc` stays as a table name. It's the register's own term, and it covers beneficial owners too, because they come from the same snapshot.
