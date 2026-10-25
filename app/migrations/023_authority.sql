-- مستويات صلاحية مهندس المشروع وتقييمه الآلي (الدستور، البند 4.4).
CREATE TABLE engineer_levels (
    user_id   INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    level     TEXT NOT NULL CHECK (level IN ('full','restricted','suspended')),
    reason    TEXT NOT NULL,
    set_at    TEXT NOT NULL,
    set_by    INTEGER NOT NULL REFERENCES users(id)
);

CREATE TABLE authority_changes (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    from_level  TEXT NOT NULL,
    to_level    TEXT NOT NULL,
    reason      TEXT NOT NULL,
    set_at      TEXT NOT NULL,
    set_by      INTEGER NOT NULL REFERENCES users(id)
);

ALTER TABLE daily_reports ADD COLUMN needs_pm INTEGER NOT NULL DEFAULT 0;
ALTER TABLE daily_reports ADD COLUMN pm_checked_at TEXT;
ALTER TABLE daily_reports ADD COLUMN pm_checked_by INTEGER REFERENCES users(id);
ALTER TABLE daily_reports ADD COLUMN times_returned INTEGER NOT NULL DEFAULT 0;
