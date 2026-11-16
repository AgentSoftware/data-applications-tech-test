-- Run history and data issues. Append-only: kept across runs, including failed ones (ADR 0012).
CREATE SCHEMA IF NOT EXISTS psc_audit;

CREATE TABLE IF NOT EXISTS psc_audit.pipeline_run (
    run_id                  bigserial PRIMARY KEY,
    source_file             text NOT NULL,
    source_sha256           text,
    snapshot_date           date,
    dry_run                 boolean NOT NULL DEFAULT false,
    started_at              timestamptz NOT NULL DEFAULT now(),
    finished_at             timestamptz,
    run_status              text NOT NULL DEFAULT 'running' CHECK (run_status IN ('running', 'succeeded', 'failed')),
    failure_reason          text,
    line_count              integer,
    malformed_line_count    integer,
    duplicate_record_count  integer,
    company_count           integer,
    trailer_counts          jsonb,
    parsed_counts           jsonb
);

CREATE TABLE IF NOT EXISTS psc_audit.data_issue (
    issue_id        bigserial PRIMARY KEY,
    run_id          bigint NOT NULL REFERENCES psc_audit.pipeline_run (run_id),
    check_code      text NOT NULL,
    severity        text NOT NULL CHECK (severity IN ('error', 'warning', 'info')),
    action          text NOT NULL CHECK (action IN ('rejected', 'dropped', 'fixed', 'flagged', 'not_followed')),
    source_line     integer,
    company_number  text,
    field_name      text,
    raw_value       text,
    fixed_value     text,
    details         jsonb
);
CREATE INDEX IF NOT EXISTS data_issue_run_check_idx ON psc_audit.data_issue (run_id, check_code);
CREATE INDEX IF NOT EXISTS data_issue_company_idx ON psc_audit.data_issue (company_number);
