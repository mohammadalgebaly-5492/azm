-- التقرير اليومي للموقع (الدستور، البند 4.3) ومراجعته (البند 4.4). الكميات والساعات بالألف.
CREATE TABLE daily_reports (
    id             INTEGER PRIMARY KEY,
    project_id     INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code           TEXT NOT NULL UNIQUE,                  -- P-2026-001-DSR-0001
    report_date    TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'review' CHECK (status IN ('review','approved','returned')),
    issues         TEXT,
    return_reason  TEXT,
    created_at     TEXT NOT NULL,
    created_by     INTEGER NOT NULL REFERENCES users(id),
    updated_at     TEXT,
    reviewed_at    TEXT,
    reviewed_by    INTEGER REFERENCES users(id),
    UNIQUE (project_id, report_date)
);

CREATE TABLE dsr_activities (
    report_id    INTEGER NOT NULL REFERENCES daily_reports(id) ON DELETE CASCADE,
    activity_id  INTEGER NOT NULL REFERENCES activities(id),
    PRIMARY KEY (report_id, activity_id)
);

CREATE TABLE dsr_steps (
    report_id  INTEGER NOT NULL REFERENCES daily_reports(id) ON DELETE CASCADE,
    step_id    INTEGER NOT NULL REFERENCES scope_steps(id),
    PRIMARY KEY (report_id, step_id)
);

CREATE TABLE dsr_quantities (
    report_id    INTEGER NOT NULL REFERENCES daily_reports(id) ON DELETE CASCADE,
    boq_item_id  INTEGER NOT NULL REFERENCES boq_items(id),
    qty_milli    BIGINT NOT NULL CHECK (qty_milli > 0),
    PRIMARY KEY (report_id, boq_item_id)
);

CREATE TABLE dsr_resources (
    report_id      INTEGER NOT NULL REFERENCES daily_reports(id) ON DELETE CASCADE,
    allocation_id  INTEGER NOT NULL REFERENCES allocations(id),
    hours_milli    BIGINT NOT NULL CHECK (hours_milli > 0 AND hours_milli <= 24000),
    idle_reason    TEXT CHECK (idle_reason IS NULL OR idle_reason IN ('breakdown','no_operator','no_front','weather','other')),
    cost           BIGINT NOT NULL CHECK (cost >= 0),
    PRIMARY KEY (report_id, allocation_id)
);
