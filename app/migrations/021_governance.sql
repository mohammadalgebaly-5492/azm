-- بوابة بدء التنفيذ (الدستور، البند 4.1)، والتأخير ومسؤوليته وتكلفته (4.5)، وخطط التعافي (4.6)، والإغلاق والأرشفة (4.10).
CREATE TABLE kickoff_reviews (
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    element      TEXT NOT NULL CHECK (element IN ('schedule','boq','resources','contract','scope','subcontractors','org','documents')),
    decision     TEXT NOT NULL CHECK (decision IN ('approved','with_cr')),
    cr_id        INTEGER REFERENCES change_requests(id),
    notes        TEXT,
    decided_at   TEXT NOT NULL,
    decided_by   INTEGER NOT NULL REFERENCES users(id),
    PRIMARY KEY (project_id, element)
);
ALTER TABLE projects ADD COLUMN kickoff_at TEXT;
ALTER TABLE projects ADD COLUMN kickoff_by INTEGER REFERENCES users(id);

CREATE TABLE delays (
    id           INTEGER PRIMARY KEY,
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code         TEXT NOT NULL UNIQUE,                    -- P-2026-001-DLY-001، ومع المالك أو الظرف الخارجي P-2026-001-CLM-001
    activity_id  INTEGER REFERENCES activities(id),
    days         INTEGER NOT NULL CHECK (days > 0),
    cause        TEXT NOT NULL,
    responsible  TEXT NOT NULL CHECK (responsible IN ('company','owner','consultant','external')),
    cost_per_day BIGINT NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    created_by   INTEGER NOT NULL REFERENCES users(id)
);

CREATE TABLE recovery_plans (
    id             INTEGER PRIMARY KEY,
    project_id     INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code           TEXT NOT NULL UNIQUE,                  -- P-2026-001-RCV-01
    option         TEXT NOT NULL CHECK (option IN ('resources','overtime','fast_track','resequence')),
    description    TEXT NOT NULL,
    days_saved     INTEGER NOT NULL DEFAULT 0,
    extra_cost     BIGINT NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'review' CHECK (status IN ('review','cc_reviewed','approved','returned')),
    return_reason  TEXT,
    created_at     TEXT NOT NULL,
    created_by     INTEGER NOT NULL REFERENCES users(id),
    cc_at          TEXT,
    cc_by          INTEGER REFERENCES users(id),
    dir_at         TEXT,
    dir_by         INTEGER REFERENCES users(id)
);

CREATE TABLE closeouts (
    project_id     INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    lessons_pm     TEXT,
    lessons_cc     TEXT,
    status         TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved')),
    updated_at     TEXT NOT NULL,
    updated_by     INTEGER NOT NULL REFERENCES users(id),
    approved_at    TEXT,
    approved_by    INTEGER REFERENCES users(id)
);

INSERT INTO role_permissions(role, permission)
SELECT key, 'project.lead' FROM roles WHERE key = 'pm'
ON CONFLICT DO NOTHING;
