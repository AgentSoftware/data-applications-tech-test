# 02: Pipeline rules, issue codes and the payload contract

- Step 1 of [plan 02](../plans/02-part1-pipeline.md). It turns the ADRs into exact rules that the code and tests follow.
- Names follow [ADR 0013](../decisions/0013-naming-conventions.md). Where this spec and the plan 01 example differ, this spec wins.

## 1. Normalisation (`normalise.py`)

### 1.1 Company and registration numbers (ADRs 0005 and 0009)

There's one function for both `company_number` and `identification.registration_number`:
1. If the value is missing or not a string, return `None` (category `missing`).
2. Trim, upper-case and remove inner spaces.
3. All digits, 1 to 8 long: zero-pad to 8.
4. Two letters followed by 1 to 6 digits: zero-pad the digits to 6.
5. Valid if the result matches `^\d{8}$`, `^[A-Z]{2}\d{6}$` or `^R\d{7}$`. Otherwise return `None` (category `unrecognised`).
6. If the output differs from the input, the value was `fixed`.

| raw | result | fixed? |
|---|---|---|
| `'09090984'` | `09090984` | no |
| `' 10333133'` | `10333133` | yes |
| `'9906121'` | `09906121` | yes |
| `'oc330146'` | `OC330146` | yes |
| `'Sc19230'` | `SC019230` | yes |
| `'ZC202'` | `ZC000202` | yes |
| `'R0000134'` | `R0000134` | no |
| `'123456789'`, `'ABC123'`, `'Zc'`, `''`, `None` | `None` | (rejected or not followed) |

**Invariant:** `normalise(x) == x` for every key in the output (ADR 0005).

### 1.2 The UK test (ADR 0009)

A registration is UK if `country_registered` or `place_registered`, lower-cased, contains any of these: `england`, `wales`, `scotland`, `northern ireland`, `united kingdom`, `uk` (as a whole word), `great britain`, `companies house` or `cardiff`.

Examples:
- UK: `United Kingdom (Scotland)`, `England And Wales`, `Companies House, Cardiff`.
- Not UK: `Delaware`, `Jersey`, `Luxembourg`.
- Neither field present: `jurisdiction_missing`.

### 1.3 Dates (ADR 0008)

- `YYYY-MM-DD` is accepted as it is.
- `YYYY-MM-DDT…` (a timestamp) is cut down to the date part, and `date_timestamp_truncated` is logged.
- Anything else, including an impossible date such as `2021-02-30`, becomes `None` and is logged as `invalid_date`.
  - An invalid `notified_on` makes the record **not active**.
  - An invalid `ceased_on` makes the record **ceased**. Both are the conservative readings.
- **Snapshot date:** the date part of the trailer's `generated_at`. If it differs from the date in the file name, `snapshot_date_mismatch` is logged.

## 2. Records (`parse.py`)

### 2.1 Kinds

| kind | psc_type | payload list | followable? |
|---|---|---|---|
| individual-person-with-significant-control | individual | `people` | |
| individual-beneficial-owner | individual | `people` | |
| super-secure-person-with-significant-control | super_secure | `protected` | |
| corporate-entity-person-with-significant-control | corporate | `companies` or `unfollowed` | yes |
| corporate-entity-beneficial-owner | corporate | `companies` or `unfollowed` | yes |
| legal-person-person-with-significant-control | legal_person | `other_controllers` | |
| legal-person-beneficial-owner (if present) | legal_person | `other_controllers` | |
| persons-with-significant-control-statement | (`psc_statement` table) | `statements` | |
| exemptions | (`psc_exemption` table) | `exemptions` | |
| totals#persons-of-significant-control-snapshot | (trailer, not data) | | |
| anything else | rejected, `unknown_kind` | | |

### 2.2 The active rule

A record is active when `notified_on <= snapshot_date` **and** (`ceased_on` is null **or** `ceased_on > snapshot_date`). Super-secure records are active when `ceased` isn't `true`.

### 2.3 Fields kept (ADR 0011)

| table | fields |
|---|---|
| `psc` | name, birth_year, birth_month, natures_of_control, notified_on, ceased_on (and the raw value), kind, psc_type, registration_number (and the raw value), country_registered, place_registered, legal_form, description (super-secure only), self_link, source_line, line_hash |
| `psc_statement` | statement_code (the source `statement` value), notified_on, ceased_on |
| `psc_exemption` | exemption_details (the source `exemptions` object) |

Everything else is ignored.

### 2.4 Duplicates (ADR 0010)

- **Exact duplicates:** the same `line_hash` (blake2b-16 of the line with trailing whitespace removed). We keep the first and log `duplicate_record`.
- **Conflicting duplicates:** the same `self_link`, different hash. If exactly one copy is ceased, we keep that copy; otherwise the first. We log `conflicting_duplicate` on every copy.

## 3. Issue codes

- One `data_issue` row per finding.
- **sev:** E = error, W = warning, I = info.
- **Fails run:** see [ADR 0012](../decisions/0012-when-the-run-fails.md). A dash means it never fails the run.

### 3.1 Per line or record

| check_code | sev | action | when | fails run |
|---|---|---|---|---|
| malformed_json | E | rejected | the line isn't valid JSON | if more than 0.1% of lines |
| unknown_kind | E | rejected | `data.kind` is missing or not in 2.1 | – |
| missing_company_number | E | rejected | there's no `company_number` | – |
| unrecognised_company_number | E | rejected | it fails 1.1 | – |
| company_number_normalised | I | fixed | 1.1 changed the value | – |
| duplicate_record | I | dropped | 2.4 | – |
| conflicting_duplicate | W | flagged (kept copy) / dropped (others) | 2.4 | – |
| date_timestamp_truncated | I | fixed | 1.3 | – |
| invalid_date | W | flagged | 1.3 | – |
| ceased_before_notified | W | flagged | `ceased_on < notified_on` | – |
| notified_after_snapshot | W | flagged | `notified_on > snapshot_date` | – |
| missing_birth_date | I | flagged | an active individual with no usable `date_of_birth` (missing, or the month isn't 1 to 12) | – |
| duplicate_trailer | W | flagged | more than one totals line; the last one is used | – |
| implausible_birth_date | W | flagged | an active individual younger than 16 on the snapshot date (using the month) | – |
| missing_natures_of_control | I | flagged | an active PSC (not super-secure) with no natures | – |

### 3.2 Per corporate link (`graph.py`, ADR 0009)

All of these have action `not_followed` and severity W, except the normalisation fix, which is `fixed` and I.

| check_code | when |
|---|---|
| registration_number_normalised | 1.1 changed the value (I, fixed; the link may still be followed) |
| no_registration_number | there's no number |
| jurisdiction_missing | there's a number, but no country and no place |
| non_uk_registration | not UK under 1.2, and the number doesn't match a company in the snapshot |
| foreign_number_collision | not UK under 1.2, but the normalised number matches a company in the snapshot |
| unrecognised_registration_number | UK, but the number fails 1.1 |
| uk_company_not_in_snapshot | UK, with a valid number that isn't a `company_number` in the file |
| self_ownership | UK, and the number is the owned company itself |

Each check runs only on **active** corporate PSCs. A ceased link is never followed and isn't an issue.

### 3.3 Graph (`graph.py`, ADR 0001)

| check_code | sev | action | when |
|---|---|---|---|
| cycle | W | flagged | once per strongly connected group of more than one company. `details` lists the companies. |
| depth_cap_reached | W | flagged | BFS stops at level 50 for a starting company |

### 3.4 Run (`build.py`, ADR 0012)

These go in `data_issue` with no line, and are summarised in `pipeline_run`:

| check_code | sev | fails run |
|---|---|---|
| input_missing | E | always |
| trailer_missing | E | always |
| trailer_count_mismatch | W or E | E (fails) if the gap is more than 0.1% for any of psc, statement or exemption; W if it's non-zero but within that |
| malformed_share_exceeded | E | always (it's the run-level form of malformed_json) |
| snapshot_date_mismatch | W | – |
| unfollowed_share_high | W | – (more than 15% of active corporate links not followed) |
| unreachable_serving_key | E | always |
| empty_output | E | always |

**Reconciliation**, for each kind group (psc, statement, exemption):

**gap = trailer count − distinct parsed records − malformed lines whose kind was recovered as that group.**

Exact duplicates aren't added back. The profile shows the trailer counts distinct records: psc 44,726 = 44,723 + 3 malformed.

## 4. Graph and levels (`graph.py`)

- **Edges:** `owned_company_number → owner_company_number`, for each active corporate PSC with `link_status = followed`.
- **BFS from each company:**
  - The company itself is level 0.
  - A company first reached at level *k* gets `level = k`, `via_company_numbers` (the path of the first route found; edges are tried in `source_line` order) and `route_count` (the sum of the counts of the parents one level below that reach it).
  - A company is expanded only once.
  - The maximum level is 50.
- **Stored** in `company_ancestor` as one row for each (start company, reached company).

## 5. The payload contract (`build.py`)

Lists are in `source_line` order, so the output is deterministic. Fields that are null or empty lists are left out, except `via` (always present, `[]` at level 0) and `levels` (always present, `[]` when nothing is active). Every entry carries `route_count`, the number of shortest routes to its company.

```text
{
  company_number, snapshot_date,
  control_status:  ok | exempt | psc_statement_only | no_active_psc,
  levels: [ { level,
              people:            [ {name, kind, birth_year, birth_month, natures_of_control, notified_on, company_number, via} ],
              protected:         [ {kind, description, company_number, via} ],
              companies:         [ {name, owner_company_number, natures_of_control, notified_on, company_number, via, route_count, already_at_level?, not_expanded?} ],
              other_controllers: [ {name, kind, legal_form, natures_of_control, notified_on, company_number, via} ],
              unfollowed:        [ {name, kind, registration_number_raw, country_registered, reason, company_number, via} ],
              statements:        [ {statement_code, notified_on, company_number, via} ],
              exemptions:        [ {exemption_details, company_number, via} ] } ],
  data_quality: { issue_count, check_codes: [...] }
}
```

- **`company_number`** on each entry is the company the registration belongs to (the company at that level). **`via`** is the path from the requested company to that company, not including the requested company. It's `[]` at level 0.
- **`companies`** entries are the followed corporate registrations at that level. `owner_company_number` is the company they point to, whose registrations make up the next level. If that company was already placed at a level less than or equal to this one (a cycle, or another route), the entry carries `already_at_level` and isn't expanded again. That's how a cycle shows up in the answer without looping. If the depth cap stopped the BFS before that company, the entry carries `not_expanded: "depth_cap"` instead.
- **A level** appears only if at least one list in it isn't empty.
- **`control_status`** is worked out from level 0 only, taking the first that applies:
  - `ok` if level 0 has any entry in `people`, `protected`, `companies`, `other_controllers` or `unfollowed`;
  - otherwise `exempt` if there are active exemptions;
  - otherwise `psc_statement_only` if there are active statements;
  - otherwise `no_active_psc`.
- **`data_quality`** covers **warning and error** issues on records of the companies in this answer (every level), plus `cycle` issues that involve them. Info-level fixes (for example a leading zero added) and run-level issues aren't included; they're all still in `data_issue`. (User decision, 2026-11-14.)

## 6. The run summary (printed)

```
PSC pipeline run 12: SUCCEEDED (published)
snapshot 2026-10-29  lines 48,154  records 47,674  companies 29,125
reconciliation  psc 44,726 = 44,723 + 3 malformed  statements 2,935 = 2,935  exemptions 16 = 16
issues by check_code and action:
  company_number_normalised   fixed         715
  duplicate_record            dropped       476
  ...
fail rules: all passed
```

## 7. Fixtures and expected results

### 7.1 `tests/fixtures/zz_example.jsonl` (hand-written)

This is plan 01, section 5.1, with these expected results:
- **psc:** 8 rows. **ownership_link:** 3 rows (2 followed, 1 `non_uk_registration`). **company_ancestor** for ZZ000001: ZZ000001 at 0, ZZ000002 at 1, ZZ000003 at 2.
- **data_issue:**
  - `registration_number_normalised` (line 5)
  - `non_uk_registration` (line 7)
  - `duplicate_record` (line 9)

  There's no issue for Dan, who is ceased.
- **Payload for ZZ000001:**
  - `control_status = ok`
  - level 0: `people` [Ada], `companies` [Two Ltd → ZZ000002]
  - level 1: `people` [Bo], `companies` [Three Ltd → ZZ000003]
  - level 2: `people` [Cy], `protected` [1], `unfollowed` [Acme Inc, `non_uk_registration`]
  - the golden file is `tests/fixtures/zz_example_ZZ000001.json`, written by hand from this spec

### 7.2 `tests/fixtures/real_cycle.jsonl` (copied from `data/`, lines 10536, 15134, 25011 and 43812)

| line | company | registration | links to | state |
|---|---|---|---|---|
| 10536 | 05104525 | Nominee Solutions Limited | 09090984 | active |
| 43812 | 09090984 | Companiesmadesimple Limited | 05104525 | active |
| 15134 | 09090984 | Westco Nominees Limited | 02889173 | ceased |
| 25011 | 02889173 | Nominee Solutions Limited | 09090984 | active |

Expected:
- One `cycle` issue for {05104525, 09090984}. The 02889173 → 09090984 edge isn't part of the cycle, because the 09090984 → 02889173 link is ceased.
- **Payload for 09090984:**
  - `control_status = ok`
  - level 0: `companies` [Companiesmadesimple Limited → 05104525]
  - level 1: `companies` [Nominee Solutions Limited → 09090984, `already_at_level: 0`]
  - no level 2, and no people at all
- **Payload for 02889173:**
  - level 0: `companies` [→ 09090984]
  - level 1: `companies` [→ 05104525]
  - level 2: `companies` [→ 09090984, `already_at_level: 1`]

### 7.3 `tests/fixtures/real_deep_chain.jsonl` (copied from `data/`: every record of the 23 companies from 04555610 up to 10003599)

Expected for 04555610:
- 23 levels (0 to 22). Levels 0 to 21 each have a followed `companies` entry that points one level up.
- Level 22: `statements` [`no-individual-or-entity-with-signficant-control`, company 10003599]. The spelling "signficant" is the source's.
- Ceased links, for example 04555609 → 00057987 (line 33096) and the Norose links at 12149330 and 11398252, don't appear.
- `route_count = 1` everywhere.

The test asserts the level count, the top-level statement, and `via` at level 22, which has 22 company numbers.

## 8. Not decided here

- The exact SQL types and constraints. They're in `sql/schema.sql` (step 8).
