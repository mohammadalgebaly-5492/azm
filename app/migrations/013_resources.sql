-- الموارد (الدستور، البند 3.6): سجل الأفراد والأطقم والمعدات على مستوى الشركة، والهيكل التنظيمي لكل مشروع،
-- وتخصيص الأفراد والأطقم والمعدات ومقاولي الباطن للمشاريع. المبالغ بالهللة، والكميات بالألف، والنسب بأجزاء من عشرة آلاف.
CREATE TABLE people (
    id               INTEGER PRIMARY KEY,
    code             TEXT NOT NULL UNIQUE,                 -- EMP-ENG-0001
    full_name        TEXT NOT NULL,
    profession_code  TEXT NOT NULL,
    job_title_code   TEXT NOT NULL,
    id_no            TEXT NOT NULL,
    nationality      TEXT,
    phone            TEXT NOT NULL,
    email            TEXT,
    daily_cost       BIGINT NOT NULL CHECK (daily_cost >= 0),
    user_id          INTEGER UNIQUE REFERENCES users(id),
    status           TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','leave','terminated')),
    created_at       TEXT NOT NULL,
    created_by       INTEGER NOT NULL REFERENCES users(id)
);

CREATE TABLE crews (
    id              INTEGER PRIMARY KEY,
    code            TEXT NOT NULL UNIQUE,                  -- CRW-CNC-001
    name            TEXT NOT NULL,
    specialty_code  TEXT NOT NULL,
    leader_id       INTEGER NOT NULL REFERENCES people(id),
    daily_cost      BIGINT CHECK (daily_cost IS NULL OR daily_cost >= 0),  -- فارغ = مجموع أفراده
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TEXT NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES users(id)
);

CREATE TABLE crew_members (
    crew_id    INTEGER NOT NULL REFERENCES crews(id) ON DELETE CASCADE,
    person_id  INTEGER NOT NULL REFERENCES people(id),
    PRIMARY KEY (crew_id, person_id)
);

CREATE TABLE equipment (
    id             INTEGER PRIMARY KEY,
    code           TEXT NOT NULL UNIQUE,                   -- EQP-SSL-0001
    catalog_code   TEXT NOT NULL,
    label          TEXT,
    make_model     TEXT,
    plate_serial   TEXT NOT NULL,
    ownership      TEXT NOT NULL CHECK (ownership IN ('owned','rented')),
    lessor         TEXT,
    daily_cost     BIGINT NOT NULL CHECK (daily_cost >= 0),
    status         TEXT NOT NULL DEFAULT 'working' CHECK (status IN ('working','maintenance','out')),
    created_at     TEXT NOT NULL,
    created_by     INTEGER NOT NULL REFERENCES users(id)
);

-- الهيكل التنظيمي للمشروع: كل سطر وظيفة، والمدير المباشر وظيفة أخرى في نفس المشروع
CREATE TABLE project_positions (
    id              INTEGER PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code            TEXT NOT NULL UNIQUE,                  -- P-2026-001-ORG-01
    job_title_code  TEXT NOT NULL,
    reports_to      INTEGER REFERENCES project_positions(id),
    person_id       INTEGER NOT NULL REFERENCES people(id),
    from_date       TEXT NOT NULL,
    to_date         TEXT,
    duties          TEXT,
    created_at      TEXT NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES users(id),
    CHECK (to_date IS NULL OR to_date >= from_date)
);
CREATE INDEX project_positions_project ON project_positions(project_id);

CREATE TABLE allocations (
    id                INTEGER PRIMARY KEY,
    project_id        INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code              TEXT NOT NULL UNIQUE,                -- P-2026-001-ALC-0001
    resource_kind     TEXT NOT NULL CHECK (resource_kind IN ('person','crew','equipment','subcontractor')),
    person_id         INTEGER REFERENCES people(id),
    crew_id           INTEGER REFERENCES crews(id),
    equipment_id      INTEGER REFERENCES equipment(id),
    entity_id         INTEGER REFERENCES entities(id),
    position_id       INTEGER REFERENCES project_positions(id),
    wbs_id            INTEGER NOT NULL REFERENCES wbs_nodes(id),
    boq_item_id       INTEGER NOT NULL REFERENCES boq_items(id),
    supervisor_id     INTEGER NOT NULL REFERENCES project_positions(id),
    from_date         TEXT NOT NULL,
    to_date           TEXT NOT NULL,
    days_per_week     INTEGER NOT NULL CHECK (days_per_week BETWEEN 1 AND 7),
    hours_per_day     INTEGER NOT NULL CHECK (hours_per_day BETWEEN 1 AND 24),
    allocation_bp     INTEGER NOT NULL CHECK (allocation_bp BETWEEN 1 AND 10000),
    qty_milli         BIGINT NOT NULL CHECK (qty_milli > 0),
    productivity_milli BIGINT NOT NULL CHECK (productivity_milli > 0),
    unit_rate         BIGINT CHECK (unit_rate IS NULL OR unit_rate >= 0),
    status            TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','approved','active','done','cancelled')),
    notes             TEXT,
    change_reason     TEXT,
    created_at        TEXT NOT NULL,
    created_by        INTEGER NOT NULL REFERENCES users(id),
    approved_at       TEXT,
    approved_by       INTEGER REFERENCES users(id),
    CHECK (to_date >= from_date)
);
CREATE INDEX allocations_project ON allocations(project_id);

-- مسميات وظيفية لأعمال الموقع (تكمل دليل المسميات في 011؛ لا تتعارض مع ما أضافه المسؤول)
INSERT INTO catalog_items(kind, code, name_ar, name_en, parent_code, cost_unit, sort) VALUES
    ('job_title', 'SAF', 'مسؤول السلامة', 'Safety officer', NULL, NULL, 80),
    ('job_title', 'FRM', 'رئيس عمال', 'Foreman', NULL, NULL, 90),
    ('job_title', 'CRP', 'نجار', 'Carpenter', NULL, NULL, 100),
    ('job_title', 'SFX', 'حداد مسلح', 'Steel fixer', NULL, NULL, 110),
    ('job_title', 'MSN', 'بنّاء', 'Mason', NULL, NULL, 120),
    ('job_title', 'ELC', 'كهربائي', 'Electrician', NULL, NULL, 130),
    ('job_title', 'PLB', 'سبّاك', 'Plumber', NULL, NULL, 140),
    ('job_title', 'EQO', 'مشغّل معدات', 'Equipment operator', NULL, NULL, 150),
    ('job_title', 'DRV', 'سائق', 'Driver', NULL, NULL, 160),
    ('job_title', 'LBR', 'عامل', 'Labourer', NULL, NULL, 170)
ON CONFLICT (kind, code) DO NOTHING;
