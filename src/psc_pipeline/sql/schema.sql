-- Clean and serving tables (plan 01, ADR 0013). Created in psc_staging, then swapped in as psc.
-- Names are unqualified: the loader sets search_path to psc_staging.

CREATE TABLE company (
    company_number  text PRIMARY KEY,
    control_status  text NOT NULL CHECK (control_status IN ('ok', 'exempt', 'psc_statement_only', 'no_active_psc')),
    run_id          bigint NOT NULL
);

CREATE TABLE psc (
    source_line              integer PRIMARY KEY,
    line_hash                text NOT NULL,
    company_number           text NOT NULL REFERENCES company,
    company_number_raw       text,
    kind                     text NOT NULL,
    psc_type                 text NOT NULL CHECK (psc_type IN ('individual', 'corporate', 'legal_person', 'super_secure')),
    name                     text,
    birth_year               smallint,
    birth_month              smallint,
    natures_of_control       text[] NOT NULL,
    notified_on              date,
    ceased_on                date,
    ceased_on_raw            text,
    is_active                boolean NOT NULL,
    registration_number_raw  text,
    registration_number      text,
    country_registered       text,
    place_registered         text,
    legal_form               text,
    description              text,
    self_link                text,
    run_id                   bigint NOT NULL
);
CREATE INDEX psc_company_idx ON psc (company_number);

CREATE TABLE psc_statement (
    source_line         integer PRIMARY KEY,
    line_hash           text NOT NULL,
    company_number      text NOT NULL REFERENCES company,
    company_number_raw  text,
    statement_code      text,
    notified_on         date,
    ceased_on           date,
    ceased_on_raw       text,
    is_active           boolean NOT NULL,
    self_link           text,
    run_id              bigint NOT NULL
);

CREATE TABLE psc_exemption (
    source_line         integer PRIMARY KEY,
    line_hash           text NOT NULL,
    company_number      text NOT NULL REFERENCES company,
    company_number_raw  text,
    exemption_details   jsonb,
    self_link           text,
    run_id              bigint NOT NULL
);

CREATE TABLE ownership_link (
    source_line           integer PRIMARY KEY REFERENCES psc,
    owned_company_number  text NOT NULL REFERENCES company,
    owner_company_number  text REFERENCES company,
    link_status           text NOT NULL,
    run_id                bigint NOT NULL,
    CHECK ((link_status = 'followed') = (owner_company_number IS NOT NULL))
);

CREATE TABLE company_ancestor (
    company_number           text NOT NULL REFERENCES company,
    ancestor_company_number  text NOT NULL REFERENCES company,
    level                    smallint NOT NULL,
    via_company_numbers      text[] NOT NULL,
    route_count              integer NOT NULL,
    PRIMARY KEY (company_number, ancestor_company_number)
);

-- The one lookup: SELECT payload FROM psc.psc_by_company WHERE company_number = $1
CREATE TABLE psc_by_company (
    company_number  text PRIMARY KEY REFERENCES company,
    payload         jsonb NOT NULL,
    run_id          bigint NOT NULL
);
