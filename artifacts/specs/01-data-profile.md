# 01: Data profile

Status: **findings, ready for review**.
Script: [`scripts/profile_data.py`](../../scripts/profile_data.py). It's read-only and streaming: it reads one line at a time and never loads the file. On the sample it takes about 2 s and 60 MB.

```
python3 scripts/profile_data.py data/persons-with-significant-control-snapshot-2026-10-29-sample.txt.gz --out /tmp/profile.md
```

The full generated report is in the **Appendix** below. This first part says what it means for the design.

## Key findings

1. **The trailer reconciles exactly once we explain the gaps.**
   - After removing 476 exact duplicates, statements (2,935) and exemptions (16) match the trailer.
   - PSCs come to 44,723 against the trailer's 44,726. The gap of 3 is the 3 malformed JSON lines. All three can be identified as individual PSCs from their raw text.
   - So the check holds: distinct parsed records plus rejected lines equal the trailer. That's the pipeline's main completeness check.
2. **Malformed lines (3).** One is missing a delimiter and two contain raw control characters. They're the only records we can't use. Each must become a `data_issue` row with its line number.
3. **Exact duplicates (476 pairs, all identical).** No record shares a `links.self` with different content, but the pipeline should still detect that case.
4. **`company_number` needs normalising** in 716 records:
   - 485 have padding spaces,
   - 181 are short digit strings that need zero-padding to 8 characters,
   - 49 are lower case,
   - 1 is unrecognised: `R0000134`, an old Northern Ireland style number. Keep it as it is and flag it.

   Self links always agree with the normalised number. The prefixes seen are SC, OC, OE (overseas entities), NI, SL, SO, NC and ZC.
5. **Dates:**
   - 107 records have `ceased_on` before `notified_on`.
   - 4 have `ceased_on` as a timestamp.
   - 1 has `notified_on` after the snapshot date (2026-12-31).
   - 43 have `notified_on` before the PSC regime started (6 April 2016). All are OE overseas entities, so this is probably legitimate for the overseas-entity register: flag it at info level only.
   - 38 individuals are younger than 16 and 21 have no date of birth.
   - 10 individuals have no `natures_of_control`.
6. **Linking a corporate PSC to a company** (8,673 active corporate links):
   - 7,861 can be followed.
   - 358 are non-UK registrations.
   - 239 have no registration number.
   - 123 are UK companies that aren't in the snapshot.
   - **41 are non-UK numbers that collide with a UK company in the file.** For example Goldman Sachs Group, Inc. (Delaware `2923466`) would become `02923466`. A naive join links these to the wrong company.
   - 32 are UK numbers in a format we don't yet recognise, such as `Sc19230` and `Sl32751`. These are prefix plus short digits and need zero-padding after the prefix, so the normaliser has to handle them.
   - 19 are self-ownership.
   - `country_registered` is free text: England, United Kingdom, Uk, England & Wales, "United Kingdom (England And Wales)", and 268 with no value. Deciding whether a registration is UK needs a rule (D3), and it has to look at `place_registered` too.
7. **The graph is a graph, not a set of chains.**
   - There are 42 cycles covering 118 companies. Most are pairs, the largest has 14.
   - 879 companies reach an owner already visited during their walk, through a cycle or a second route to the same owner.
   - The deepest walk reaches **level 22**. Companies can have several corporate owners: one company has 24 companies above it.
8. **Chains can end with nobody.** The 22-level Spirit Pubs / Greene King / CK chain ends at `10003599`, whose only record is an active statement: *no individual or entity with significant control*. So statements have to go into the response, otherwise the API returns 22 empty levels with no explanation.
9. **Person identity.** 451 active (name, date of birth) identities appear in more than one record. That supports de-duplicating people within a response by name plus date of birth, as `data/README.md` says fake details are consistent. It's a heuristic: two different people can share a name and date of birth.

## What this means for the pipeline

| Finding | Pipeline behaviour (proposed) | `data_issue` action |
|---|---|---|
| Malformed line | Reject the line and keep its line number and kind if recoverable | `rejected` |
| Exact duplicate | Keep the first copy | `dropped_duplicate` |
| Same `self` link, different content | Keep one by a fixed rule and log both | `conflict_resolved` |
| `company_number` padding, case or short digits | Normalise. Keep the raw value next to the clean one | `fixed` |
| Unrecognised company number | Keep the raw value as the key | `flagged` |
| `ceased_on` timestamp | Parse to a date | `fixed` |
| `ceased_on` before `notified_on` | Treat as ceased | `flagged` |
| `notified_on` after the snapshot date | Treat as not yet active | `excluded_from_now` |
| Non-UK registration, or a colliding non-UK number | Don't follow. Show as a controller we couldn't follow | `unfollowable` |
| No registration number, or UK company not in the snapshot | Don't follow. Show as a controller we couldn't follow | `unfollowable` |
| Self-ownership or a cycle | BFS visited set stops it. Log the edge | `cycle_detected` |
| Trailer mismatch not explained by rejected lines | **Fail the run** | `fatal` |

## Appendix: generated report (`scripts/profile_data.py`, run on 2026-11-13)

Snapshot date: **2026-10-29**. Lines read: **48,154**. Distinct records: **47,674**. Companies (normalised): **29,125**.

### 1. Parsing and structure

- Malformed JSON lines: **3**
  - line 1144: Expecting ',' delimiter at char 840; kind recoverable from raw text: `individual-person-with-significant-control`
  - line 27119: Invalid control character at at char 1141; kind recoverable from raw text: `individual-person-with-significant-control`
  - line 41356: Invalid control character at at char 1171; kind recoverable from raw text: `individual-person-with-significant-control`
- Trailer (`totals#persons-of-significant-control-snapshot`) at line 48154 of 48154 (last line)

### 2. Kinds (distinct records)

| kind | records | active | ceased |
|---|---|---|---|
| individual-person-with-significant-control | 32,791 | 25,568 | 7,223 |
| corporate-entity-person-with-significant-control | 11,680 | 8,637 | 3,043 |
| persons-with-significant-control-statement | 2,935 | 1,539 | 1,396 |
| legal-person-person-with-significant-control | 105 | 64 | 41 |
| individual-beneficial-owner | 63 | 55 | 8 |
| corporate-entity-beneficial-owner | 47 | 36 | 11 |
| super-secure-person-with-significant-control | 37 | 33 | 4 |
| exemptions | 16 | 16 | 0 |

### 3. Key sets per kind

'Always' means present in every record of that kind. Optional keys show how often they appear.

| kind | distinct key sets | always | optional (share) |
|---|---|---|---|
| individual-person-with-significant-control | 11 | address, etag, kind, links, name, name_elements, nationality, notified_on | country_of_residence (100%), natures_of_control (100%), date_of_birth (100%), identity_verification_details (52%), ceased_on (22%) |
| corporate-entity-person-with-significant-control | 2 | address, etag, identification, kind, links, name, natures_of_control, notified_on | ceased_on (26%) |
| persons-with-significant-control-statement | 2 | etag, kind, links, notified_on, statement | ceased_on (48%) |
| legal-person-person-with-significant-control | 2 | address, etag, identification, kind, links, name, natures_of_control, notified_on | ceased_on (39%) |
| individual-beneficial-owner | 3 | address, date_of_birth, etag, kind, links, name, name_elements, nationality, natures_of_control, notified_on | is_sanctioned (98%), ceased_on (13%) |
| corporate-entity-beneficial-owner | 2 | address, etag, identification, is_sanctioned, kind, links, name, natures_of_control, notified_on, principal_office_address | ceased_on (23%) |
| super-secure-person-with-significant-control | 2 | ceased, description, etag, kind, links | ceased_on (11%) |
| exemptions | 1 | etag, exemptions, kind, links | none |

### 4. Company-number formats (`company_number`)

| format | records | examples (line: raw value) |
|---|---|---|
| canonical | 46,958 |  |
| whitespace | 485 | 9: `' 10333133'`; 145: `'13405766 '`; 254: `' 10282122'` |
| short_digits | 181 | 11: `'9906121'`; 44: `'3579143'`; 157: `'3732995'` |
| lowercase | 49 | 419: `'oc330146'`; 528: `'sc022163'`; 3610: `'so305976'` |
| unrecognised | 1 | 6624: `'R0000134'` |

- Letter prefixes: SC 2186, OC 1294, OE 586, NI 576, SL 331, SO 112, NC 4, ZC 3
- Records whose self-link company differs from `company_number` after normalising: 0

### 5. Dates and other field problems

| field | problem | records | examples (line, company, value) |
|---|---|---|---|
| notified_on | before_psc_regime_2016_04_06 | 43 | 10285, OE008120, `2015-07-24`; 11296, OE021510, `2016-04-01`; 14939, OE022687, `2015-09-10` |
| ceased_on | timestamp_not_date | 4 | 6106, 07866172, `2026-09-22T00:00:00Z`; 19232, 08733441, `2021-07-29T00:00:00Z`; 34356, OC425818, `2022-04-01T00:00:00Z` |
| notified_on | after_snapshot_date | 1 | 41182, 01277725, `2026-12-31` |

- `ceased_on` earlier than `notified_on`: **107**
- Individuals with no `natures_of_control`: {'individual-person-with-significant-control': 10}
- Individual date-of-birth problems: {'younger_than_16': 38, 'missing': 21}

### 6. Duplicates

- Exact duplicate records (identical JSON): **476**. Examples (first line, duplicate line): [(604, 2446), (1273, 3672), (974, 4922)]
- Same `links.self`, different content: **0** []
- Active individuals whose (name, date of birth) appears in more than one record: 451 identities. This is the person-identity question for de-duplication.

### 7. Trailer reconciliation

| category | trailer says | distinct records parsed | difference |
|---|---|---|---|
| psc | 44726 | 44723 | 3 |
| statements | 2935 | 2935 | 0 |
| exemptions | 16 | 16 | 0 |

Malformed lines that couldn't be counted: 3. Trailer `generated_at`: 2026-10-29T07:08:01Z

### 8. Statements (active and ceased)

| statement | active | records |
|---|---|---|
| no-individual-or-entity-with-signficant-control | True | 1341 |
| no-individual-or-entity-with-signficant-control | False | 745 |
| all-beneficial-owners-identified | False | 168 |
| steps-to-find-psc-not-yet-completed | False | 162 |
| nobody-has-become-or-ceased-to-be-a-beneficial-owner | False | 114 |
| nobody-has-become-or-ceased-to-be-a-beneficial-owner | True | 68 |
| all-beneficial-owners-identified | True | 65 |
| psc-details-not-confirmed | False | 62 |
| psc-exists-but-not-identified | False | 52 |
| no-beneficial-owner-identified | False | 27 |
| steps-to-find-psc-not-yet-completed-partnership | False | 26 |
| psc-contacted-but-no-response | False | 19 |
| no-beneficial-owner-identified | True | 14 |
| psc-details-not-confirmed | True | 12 |
| somebody-has-become-or-ceased-to-be-a-beneficial-owner | False | 11 |
| psc-exists-but-not-identified | True | 8 |
| steps-to-find-psc-not-yet-completed-partnership | True | 7 |
| steps-to-find-psc-not-yet-completed | True | 6 |
| psc-contacted-but-no-response | True | 6 |
| no-individual-or-entity-with-signficant-control-partnership | True | 5 |
| somebody-has-become-or-ceased-to-be-a-beneficial-owner | True | 5 |
| awaiting-confirmation-from-psc | False | 4 |
| at-least-one-beneficial-owner-unidentified | False | 3 |
| no-individual-or-entity-with-signficant-control-partnership | False | 2 |
| psc-details-not-confirmed-partnership | False | 1 |
| at-least-one-beneficial-owner-unidentified | True | 1 |
| awaiting-confirmation-from-psc | True | 1 |

### 9. Resolving active corporate PSCs to companies

| outcome | links | examples (line, owned, name, raw reg, country) |
|---|---|---|
| followed | 7861 |  |
| non_uk_registration | 358 | 412, 10047163, Nyx Gaming Group Limited, `'51637'`, Guernsey; 442, 02594323, Sumitomo Chemical Company Ltd, `'2010001071327'`, Japan; 480, 04101344, Skanska Ab, `'556000-4615'`, Sweden |
| no_registration_number | 239 | 241, 01425540, G B Thompson Discretionary Trust, `None`, None; 317, 07143867, Barnsley Partnership For Learning 2 Ltd, `None`, None; 644, 08096651, Quicksilver Films Limited, `None`, None |
| uk_company_not_in_snapshot | 123 | 106, 03388362, The Law Debenture Corporation P.L.C., `'0030397'`, England; 183, 07266173, Icg Plc, `'02234775'`, England And Wales; 359, 09628613, Caledonia Investments Plc, `'00235481'`, Uk |
| non_uk_but_number_matches_a_company_in_file | 41 | 867, 06409662, The Goldman Sachs Group, Inc., `'2923466'`, Delaware; 1371, 06313653, Adonia Medical Group Ltd, `'08237487'`, N/A; 1945, 13613375, Alti Global, Inc, `'7213325'`, United States |
| uk_but_unrecognised_number | 32 | 1106, 11250624, Symbiotic (Investments) Lp, `'Sl32751'`, United Kingdom; 2667, 03555107, The British Standards Institution, `'Zc202'`, England And Wales; 3295, 07351242, Mitie Group Plc, `'Sc19230'`, United Kingdom (Scotland) |
| self_ownership | 19 | 975, 06172942, Norham Holdings Group Limited, `'06172942'`, England; 2248, 04408673, Kenard Group Limited, `'04408673'`, Uk; 5076, 10204501, Allied Developments (M/Cr) Limited, `'10204501'`, England |

`country_registered` values on active corporate PSCs (top 20):

`England` 2881, `United Kingdom` 2769, `England And Wales` 1381, `Scotland` 361, `England & Wales` 286, `None` 268, `Uk` 195, `United States` 54, `Northern Ireland` 39, `Wales` 38, `Switzerland` 34, `Luxembourg` 31, `Delaware` 25, `Jersey` 22, `United Kingdom (England And Wales)` 20, `France` 16, `Japan` 14, `Sweden` 14, `Germany` 14, `Canada` 12

- Active legal-person PSCs (terminal, nothing to follow): 64
- Active super-secure PSCs (identity protected): 33

### 10. Ownership graph (followed edges only)

- Companies with at least one followed corporate owner: 7,187. Edges: 7,861
- Ownership cycles (strongly connected groups larger than 1): **42**, covering 118 companies. Sizes: [(2, 26), (3, 10), (4, 3), (5, 2), (14, 1)]
- Deepest level reached by BFS (highest controlling company level) per company: L0: 21,938, L1: 2,723, L2: 1,368, L3: 828, L4: 539, L5: 380, L6: 301, L7: 237, L8: 226, L9: 139, L10: 116, L11: 71, L12: 50, L13: 49, L14: 31, L15: 21, L16: 31, L17: 32, L18: 21, L19: 12, L20: 4, L21: 7, L22: 1
- Largest number of companies above one company: 24
- Companies whose BFS hit an already visited company (a cycle or a second route to the same owner): 879

### 11. Traced chains (BFS from a starting company)

**Start: 04555610** (levels 0 to 22, 0 edges skipped as already visited)

```
L0  04555610  [0 individual(s)]
L1  04555609  <- owns 04555610 as 'Freshwild Limited'  [0 individual(s)]
L2  04661726  <- owns 04555609 as 'Cph Palladium Limited'  [0 individual(s)]
L3  04661724  <- owns 04661726 as 'Dearg Limited'  [0 individual(s)]
L4  04700766  <- owns 04661724 as 'Narnain'  [0 individual(s)]
L5  00057987  <- owns 04700766 as 'Cleveland Place Holdings Limited'  [0 individual(s)]
L6  04872046  <- owns 00057987 as 'Spirit Retail Bidco Limited'  [0 individual(s)]
L7  05267589  <- owns 04872046 as 'Spirit Pubs Parent Limited'  [0 individual(s)]
L8  05266779  <- owns 05267589 as 'Spirit Pubs Debenture Holdings Limited'  [0 individual(s)]
L9  04271748  <- owns 05266779 as 'Spirit Parent Limited'  [0 individual(s)]
L10  04320672  <- owns 04271748 as 'Spirit Financial Holdings Limited'  [0 individual(s)]
L11  04271971  <- owns 04320672 as 'Spirit Group Equity Limited'  [0 individual(s)]
L12  04271973  <- owns 04271971 as 'Spirit Managed Holdings Limited'  [0 individual(s)]
L13  04872039  <- owns 04271973 as 'Spirit Group Parent Limited'  [0 individual(s)]
L14  04914762  <- owns 04872039 as 'Spirit Intermediate Holdings Limited'  [0 individual(s)]
L15  04872028  <- owns 04914762 as 'Spirit Group Holdings Limited'  [0 individual(s)]
L16  07662502  <- owns 04872028 as 'Spirit Pub Company (Sge) Limited'  [0 individual(s)]
L17  07662211  <- owns 07662502 as 'Spirit Pub Company (Holdco) Limited'  [0 individual(s)]
L18  07662835  <- owns 07662211 as 'Spirit Pub Company Limited'  [0 individual(s)]
L19  00024511  <- owns 07662835 as 'Greene King Plc'  [0 individual(s)]
L20  12149330  <- owns 00024511 as 'Ck Noble (Uk) Limited'  [0 individual(s)]
L21  11398252  <- owns 12149330 as 'Ck Steel (Uk) Limited'  [0 individual(s)]
L22  10003599  <- owns 11398252 as 'Cka Holdings Uk Limited'  [0 individual(s)]
```

**Start: 03539665** (levels 0 to 10, 7 edges skipped as already visited)

```
L0  03539665  [0 individual(s)]
L1  07428859  <- owns 03539665 as 'Helix Acquisition Limited'  [0 individual(s)]
L1  10852384  <- owns 03539665 as 'Betjeman Holdings Limited'  [0 individual(s)]
L2  07428829  <- owns 07428859 as 'Helix Bufferco Limited'  [0 individual(s)]
L2  10851742  <- owns 10852384 as 'Betjeman Holdings Midco Limited'  [0 individual(s)]
L3  07428762  <- owns 07428829 as 'Helix Midco Limited'  [0 individual(s)]
L3  10851599  <- owns 10851742 as 'Betjeman Holdings Jvco Limited'  [0 individual(s)]
L4  10847726  <- owns 10851599 as 'Infrastructure Investments Betjeman Limited'  [0 individual(s)]
L4  OC417797  <- owns 10851599 as 'Agincourt (1) Llp'  [0 individual(s)]
L4  10849757  <- owns 10851599 as 'Equitix Hs1 Holdings 1 Limited'  [0 individual(s)]
L5  10840284  <- owns 10847726 as 'Infrastructure Investments Betjeman (Holdco) Limited'  [0 individual(s)]
L5  OC417690  <- owns 10847726 as 'Waterloo Place (2) Gp Llp'  [0 individual(s)]
L5  03364976  <- owns OC417797 as 'Infrared Capital Partners Limited'  [0 individual(s)]
L5  07444614  <- owns OC417797 as 'Infrared Capital Partners (Holdco) Limited'  [0 individual(s)]
L5  10849503  <- owns 10849757 as 'Equitix Hs1 Holdings 2 Limited'  [0 individual(s)]
L6  05622598  <- owns 10840284 as 'Infrastructure Investments General Partner Limited'  [0 individual(s)]
L6  07073365  <- owns OC417690 as 'Infrared Capital Partners (Gp Holdco) Limited'  [0 individual(s)]
L6  OC359657  <- owns 07444614 as 'Infrared Partners Llp'  [0 individual(s)]
L6  10849335  <- owns 10849503 as 'Equitix Hs1 Holdings 3 Limited'  [0 individual(s)]
L7  03917449  <- owns 05622598 as 'Infrared (Infrastructure) Capital Partners Limited'  [0 individual(s)]
L7  12460732  <- owns OC359657 as 'Infrared (Uk) Holdco 2020 Ltd.'  [0 individual(s); cannot follow 'Sun Life Financial Inc.' (non_uk_registration)]
L7  10849899  <- owns 10849335 as 'Equitix Ma 4 Capital Eurobond Limited'  [0 individual(s)]
L8  05972500  <- owns 10849899 as 'Equitix Holdings Ltd'  [0 individual(s)]
L9  09213529  <- owns 05972500 as 'Pace Bidco Limited'  [0 individual(s)]
L10  09213524  <- owns 09213529 as 'Pace Topco Limited'  [1 individual(s)]
```

**Start: 09090984** (levels 0 to 1, 1 edges skipped as already visited)

```
L0  09090984  [0 individual(s)]
L1  05104525  <- owns 09090984 as 'Companiesmadesimple Limited'  [0 individual(s)]
```

**Start: 00236383** (levels 0 to 1, 0 edges skipped as already visited)

```
L0  00236383  [0 individual(s); cannot follow 'Exor N.V.' (non_uk_registration)]
L1  17045665  <- owns 00236383 as 'Sfc International Holdings Limited'  [1 individual(s)]
```

