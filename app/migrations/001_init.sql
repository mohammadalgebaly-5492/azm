-- المرحلة الأولى: الحسابات والجلسات والمشروعات والطاقم والسجل
-- المبالغ تُخزن بالهللة كأعداد صحيحة. التواريخ بصيغة ISO 8601 (UTC).

CREATE TABLE counters (
    key   TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);

CREATE TABLE users (
    id                   INTEGER PRIMARY KEY,
    code                 TEXT NOT NULL UNIQUE,              -- USR-PM-03
    username             TEXT NOT NULL UNIQUE,              -- يُخزن بحروف صغيرة
    email                TEXT NOT NULL UNIQUE,
    full_name            TEXT NOT NULL,
    role                 TEXT NOT NULL CHECK (role IN ('admin','pm','director','accountant','viewer','owner_rep','consultant')),
    status               TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled')),
    password_hash        TEXT NOT NULL,
    must_change_password INTEGER NOT NULL DEFAULT 1,
    failed_attempts      INTEGER NOT NULL DEFAULT 0,
    locked_until         TEXT,
    last_login_at        TEXT,
    password_changed_at  TEXT,
    phone                TEXT,
    job_title            TEXT,
    created_at           TEXT NOT NULL,
    created_by           INTEGER REFERENCES users(id)
);

CREATE TABLE sessions (
    id          INTEGER PRIMARY KEY,
    token_hash  TEXT NOT NULL UNIQUE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    ip          TEXT,
    user_agent  TEXT
);
CREATE INDEX sessions_user ON sessions(user_id);

CREATE TABLE projects (
    id               INTEGER PRIMARY KEY,
    code             TEXT NOT NULL UNIQUE,                   -- P-2026-014
    name             TEXT NOT NULL,
    client           TEXT,
    consultant       TEXT,
    location         TEXT,
    contract_no      TEXT,
    contract_value   INTEGER CHECK (contract_value IS NULL OR contract_value >= 0),
    start_date       TEXT,
    end_date         TEXT,
    status           TEXT NOT NULL DEFAULT 'setup' CHECK (status IN ('setup','active','closed')),
    created_at       TEXT NOT NULL,
    created_by       INTEGER NOT NULL REFERENCES users(id),
    CHECK (end_date IS NULL OR start_date IS NULL OR end_date > start_date)
);

CREATE TABLE project_members (
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    assigned_at  TEXT NOT NULL,
    assigned_by  INTEGER NOT NULL REFERENCES users(id),
    PRIMARY KEY (project_id, user_id)
);
CREATE INDEX project_members_user ON project_members(user_id);

-- سجل تدقيق للإضافة فقط
CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY,
    at          TEXT NOT NULL,
    actor_id    INTEGER REFERENCES users(id),
    action      TEXT NOT NULL,
    entity      TEXT,
    entity_id   INTEGER,
    project_id  INTEGER REFERENCES projects(id),
    details     TEXT,
    ip          TEXT
);
CREATE INDEX audit_project ON audit_log(project_id);
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
