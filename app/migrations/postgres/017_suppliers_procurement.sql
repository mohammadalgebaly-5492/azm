-- الموردون نوع جهة جديد (ENT-SUP-0001)، ودور «المشتريات» (الدستور، المادة 1 والبند 4.2).
ALTER TABLE entities DROP CONSTRAINT IF EXISTS entities_kind_check;
ALTER TABLE entities ADD CONSTRAINT entities_kind_check CHECK (kind IN ('owner','consultant','subcontractor','supplier'));
INSERT INTO roles(key, code, name_ar, name_en, external, system, sort)
VALUES ('procurement', 'PRC', 'المشتريات', 'Procurement', FALSE, FALSE, 35)
ON CONFLICT DO NOTHING;
