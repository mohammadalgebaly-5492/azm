-- السجلات المشتركة (الدستور، المادة 2 والبند 3.9): الأدلة، وسجل الجهات (المالك، والاستشاري، ومقاول الباطن)، وممثلو الجهة في كل مشروع

-- الأدلة: كل اسم يتكرر يُختار من هنا ولا يُكتب يدويًا. العنصر المستخدم لا يُحذف بل يُوقف.
CREATE TABLE catalog_items (
    id           INTEGER PRIMARY KEY,
    kind         TEXT NOT NULL CHECK (kind IN ('unit','doc_type','profession','specialty','job_title','equipment_type','equipment')),
    code         TEXT NOT NULL CHECK (length(code) = 3),
    name_ar      TEXT NOT NULL,
    name_en      TEXT NOT NULL,
    parent_code  TEXT,                                   -- للمعدة: كود نوعها
    cost_unit    TEXT CHECK (cost_unit IS NULL OR cost_unit IN ('day','hour')),
    active       BOOLEAN NOT NULL DEFAULT TRUE,
    sort         INTEGER NOT NULL DEFAULT 100,
    UNIQUE (kind, code)
);

-- الجهات: قائمة واحدة لكل الشركة، والجهة تتكرر في أكثر من مشروع
CREATE TABLE entities (
    id               INTEGER PRIMARY KEY,
    code             TEXT NOT NULL UNIQUE,              -- ENT-OWN-0001
    kind             TEXT NOT NULL CHECK (kind IN ('owner','consultant','subcontractor')),
    name             TEXT NOT NULL,
    name_en          TEXT,
    email            TEXT NOT NULL,
    phone            TEXT,
    website          TEXT,
    cr_no            TEXT,                               -- السجل التجاري
    vat_no           TEXT,                               -- الرقم الضريبي
    classification   TEXT,                               -- درجة التصنيف
    approval_status  TEXT CHECK (approval_status IS NULL OR approval_status IN ('approved','review','suspended')),
    notes            TEXT,
    active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TEXT NOT NULL,
    created_by       INTEGER NOT NULL REFERENCES users(id)
);

CREATE TABLE entity_addresses (
    id          INTEGER PRIMARY KEY,
    entity_id   INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    label       TEXT NOT NULL CHECK (label IN ('main','branch')),
    city        TEXT NOT NULL,
    details     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX entity_addresses_entity ON entity_addresses(entity_id);

-- أشخاص الجهة: تُحفظ بياناتهم مرة واحدة، ويُختار منهم ممثلو كل مشروع
CREATE TABLE entity_people (
    id          INTEGER PRIMARY KEY,
    entity_id   INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    code        TEXT NOT NULL UNIQUE,                    -- ENT-OWN-0001-R01
    full_name   TEXT NOT NULL,
    job_title   TEXT NOT NULL,
    phone       TEXT NOT NULL,
    email       TEXT NOT NULL,
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TEXT NOT NULL
);
CREATE INDEX entity_people_entity ON entity_people(entity_id);

CREATE TABLE entity_specialties (
    entity_id       INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    specialty_code  TEXT NOT NULL,
    PRIMARY KEY (entity_id, specialty_code)
);

ALTER TABLE projects ADD COLUMN owner_entity_id INTEGER REFERENCES entities(id);
ALTER TABLE projects ADD COLUMN consultant_entity_id INTEGER REFERENCES entities(id);

-- ممثلو المالك والاستشاري في المشروع: شخصان على الأقل من كل جهة (المادة 2)
CREATE TABLE project_representatives (
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    person_id    INTEGER NOT NULL REFERENCES entity_people(id),
    assigned_at  TEXT NOT NULL,
    assigned_by  INTEGER NOT NULL REFERENCES users(id),
    PRIMARY KEY (project_id, person_id)
);

INSERT INTO catalog_items(kind, code, name_ar, name_en, parent_code, cost_unit, sort) VALUES
    ('unit', 'CBM', 'م3', 'Cubic metre', NULL, NULL, 10),
    ('unit', 'SQM', 'م2', 'Square metre', NULL, NULL, 20),
    ('unit', 'LMT', 'م.ط', 'Linear metre', NULL, NULL, 30),
    ('unit', 'TON', 'طن', 'Tonne', NULL, NULL, 40),
    ('unit', 'KGM', 'كجم', 'Kilogram', NULL, NULL, 50),
    ('unit', 'NOS', 'عدد', 'Number', NULL, NULL, 60),
    ('unit', 'LSM', 'مقطوعية', 'Lump sum', NULL, NULL, 70),
    ('unit', 'LTR', 'لتر', 'Litre', NULL, NULL, 80),
    ('doc_type', 'CTD', 'مستندات العقد', 'Contract documents', NULL, NULL, 10),
    ('doc_type', 'DRW', 'المخططات', 'Drawings', NULL, NULL, 20),
    ('doc_type', 'SPC', 'المواصفات', 'Specifications', NULL, NULL, 30),
    ('doc_type', 'PRM', 'التصاريح', 'Permits', NULL, NULL, 40),
    ('doc_type', 'LTR', 'المراسلات', 'Correspondence', NULL, NULL, 50),
    ('doc_type', 'MOM', 'المحاضر', 'Minutes of meetings', NULL, NULL, 60),
    ('doc_type', 'MAT', 'اعتمادات المواد', 'Material submittals', NULL, NULL, 70),
    ('doc_type', 'SHD', 'المخططات التنفيذية', 'Shop drawings', NULL, NULL, 80),
    ('doc_type', 'RPT', 'التقارير', 'Reports', NULL, NULL, 90),
    ('profession', 'ENG', 'مهندس', 'Engineer', NULL, NULL, 10),
    ('profession', 'SUP', 'مشرف', 'Supervisor', NULL, NULL, 20),
    ('profession', 'TEC', 'فني', 'Technician', NULL, NULL, 30),
    ('profession', 'LAB', 'عامل', 'Labourer', NULL, NULL, 40),
    ('profession', 'OPR', 'سائق ومشغّل معدات', 'Driver and operator', NULL, NULL, 50),
    ('profession', 'ADM', 'إداري', 'Administrative', NULL, NULL, 60),
    ('specialty', 'CNC', 'خرسانة', 'Concrete', NULL, NULL, 10),
    ('specialty', 'STL', 'حديد تسليح', 'Reinforcement steel', NULL, NULL, 20),
    ('specialty', 'CAR', 'نجارة', 'Carpentry', NULL, NULL, 30),
    ('specialty', 'MAS', 'مبانٍ', 'Masonry', NULL, NULL, 40),
    ('specialty', 'FIN', 'تشطيبات', 'Finishes', NULL, NULL, 50),
    ('specialty', 'ELE', 'كهرباء', 'Electrical', NULL, NULL, 60),
    ('specialty', 'MEC', 'ميكانيكا', 'Mechanical', NULL, NULL, 70),
    ('job_title', 'PJM', 'مدير مشروع', 'Project manager', NULL, NULL, 10),
    ('job_title', 'STE', 'مهندس موقع', 'Site engineer', NULL, NULL, 20),
    ('job_title', 'PLE', 'مهندس تخطيط', 'Planning engineer', NULL, NULL, 30),
    ('job_title', 'CCE', 'مهندس تحكم تكلفة', 'Cost control engineer', NULL, NULL, 40),
    ('job_title', 'SRV', 'مساح', 'Surveyor', NULL, NULL, 50),
    ('job_title', 'INS', 'مراقب أعمال', 'Works inspector', NULL, NULL, 60),
    ('job_title', 'STK', 'أمين مخزن', 'Storekeeper', NULL, NULL, 70),
    ('equipment_type', 'HVY', 'معدات ثقيلة', 'Heavy equipment', NULL, NULL, 10),
    ('equipment_type', 'LGT', 'معدات خفيفة', 'Light equipment', NULL, NULL, 20),
    ('equipment_type', 'TRN', 'معدات نقل', 'Transport equipment', NULL, NULL, 30),
    ('equipment_type', 'PWR', 'معدات الطاقة والخدمات', 'Power and service equipment', NULL, NULL, 40),
    ('equipment_type', 'TLS', 'عدد يدوية وكهربائية', 'Hand and power tools', NULL, NULL, 50),
    ('equipment', 'EXC', 'حفار', 'Excavator', 'HVY', 'day', 10),
    ('equipment', 'LDR', 'محمّلة', 'Wheel loader', 'HVY', 'day', 20),
    ('equipment', 'CRN', 'رافعة', 'Crane', 'HVY', 'day', 30),
    ('equipment', 'DOZ', 'جرافة', 'Bulldozer', 'HVY', 'day', 40),
    ('equipment', 'SSL', 'محمّلة صغيرة', 'Skid steer loader', 'LGT', 'day', 50),
    ('equipment', 'MIX', 'خلاطة خرسانة', 'Concrete mixer', 'LGT', 'day', 60),
    ('equipment', 'VIB', 'هزاز خرسانة', 'Concrete vibrator', 'LGT', 'day', 70),
    ('equipment', 'RLR', 'مدحلة صغيرة', 'Small roller', 'LGT', 'day', 80),
    ('equipment', 'TRK', 'شاحنة', 'Truck', 'TRN', 'day', 90),
    ('equipment', 'DMP', 'قلّاب', 'Dump truck', 'TRN', 'day', 100),
    ('equipment', 'WTK', 'صهريج مياه', 'Water tanker', 'TRN', 'day', 110),
    ('equipment', 'GEN', 'مولد كهرباء', 'Generator', 'PWR', 'day', 120),
    ('equipment', 'CMP', 'ضاغط هواء', 'Air compressor', 'PWR', 'day', 130),
    ('equipment', 'PMP', 'مضخة مياه', 'Water pump', 'PWR', 'day', 140),
    ('equipment', 'GRD', 'صاروخ (مجلخة)', 'Angle grinder', 'TLS', 'day', 150),
    ('equipment', 'DRL', 'مثقاب', 'Drill', 'TLS', 'day', 160),
    ('equipment', 'SAW', 'منشار كهربائي', 'Power saw', 'TLS', 'day', 170);

-- إدارة السجلات تُمنح افتراضيًا لمهندس تحكم تكلفة (الدستور: الحساب الرئيسي أو مهندس تحكم تكلفة يضيفان إلى الأدلة)
INSERT INTO role_permissions(role, permission)
SELECT key, 'registers.manage' FROM roles WHERE key = 'admin'
ON CONFLICT DO NOTHING;
