-- الجدول الزمني للمتابعة (الدستور، البند 3.4)، وإنجاز خطوات نطاق العمل (البند 3.7)، وجدول الدفعات التعاقدية (البند 3.2).
-- النسب بأجزاء من عشرة آلاف.
CREATE TABLE activities (
    id               INTEGER PRIMARY KEY,
    project_id       INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code             TEXT NOT NULL,                       -- 01.02-A010
    name             TEXT NOT NULL,
    wbs_id           INTEGER NOT NULL REFERENCES wbs_nodes(id),
    boq_item_id      INTEGER REFERENCES boq_items(id),
    planned_start    TEXT NOT NULL,
    planned_finish   TEXT NOT NULL,
    actual_start     TEXT,
    actual_finish    TEXT,
    notes            TEXT,
    created_at       TEXT NOT NULL,
    created_by       INTEGER NOT NULL REFERENCES users(id),
    UNIQUE (project_id, code),
    CHECK (planned_finish >= planned_start),
    CHECK (actual_finish IS NULL OR (actual_start IS NOT NULL AND actual_finish >= actual_start))
);
CREATE INDEX activities_project ON activities(project_id);

CREATE TABLE activity_links (
    activity_id      INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    predecessor_id   INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    PRIMARY KEY (activity_id, predecessor_id),
    CHECK (activity_id != predecessor_id)
);

ALTER TABLE projects ADD COLUMN schedule_reviewed_at TEXT;
ALTER TABLE projects ADD COLUMN schedule_reviewed_by INTEGER REFERENCES users(id);
ALTER TABLE projects ADD COLUMN schedule_approved_at TEXT;
ALTER TABLE projects ADD COLUMN schedule_approved_by INTEGER REFERENCES users(id);

ALTER TABLE scope_steps ADD COLUMN finished_on TEXT;
ALTER TABLE scope_steps ADD COLUMN finished_by INTEGER REFERENCES users(id);
ALTER TABLE allocations ADD COLUMN activity_id INTEGER REFERENCES activities(id);

CREATE TABLE payment_milestones (
    id                   INTEGER PRIMARY KEY,
    contract_id          INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    code                 TEXT NOT NULL UNIQUE,            -- P-2026-001-CON-01-PAY-01
    seq                  INTEGER NOT NULL CHECK (seq > 0),
    description          TEXT NOT NULL,
    activity_id          INTEGER NOT NULL REFERENCES activities(id),
    required_progress_bp INTEGER NOT NULL DEFAULT 10000 CHECK (required_progress_bp BETWEEN 1 AND 10000),
    share_bp             INTEGER NOT NULL CHECK (share_bp BETWEEN 1 AND 10000),
    notes                TEXT,
    created_at           TEXT NOT NULL,
    created_by           INTEGER NOT NULL REFERENCES users(id)
);

INSERT INTO role_permissions(role, permission)
SELECT key, 'schedule.manage' FROM roles WHERE key IN ('admin', 'pm')
ON CONFLICT DO NOTHING;
