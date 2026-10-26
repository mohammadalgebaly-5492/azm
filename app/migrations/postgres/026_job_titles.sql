-- المسميات الوظيفية في الإنشاءات وشركات المقاولات (طلب م. محمد 2026-10-26): مجمّعة بالترتيب: الإدارة، والمهندسون،
-- والإشراف، والمكتب الفني والإدارة، والفنيون، والمشغّلون، والعمالة. لا يتغير اسم أي مسمى موجود، بل ترتيبه فقط.
INSERT INTO catalog_items(kind, code, name_ar, name_en, parent_code, cost_unit, sort) VALUES
    ('job_title', 'GMG', 'مدير عام', 'General manager', NULL, NULL, 102),
    ('job_title', 'PDR', 'مدير المشاريع', 'Projects director', NULL, NULL, 104),
    ('job_title', 'CNM', 'مدير التنفيذ', 'Construction manager', NULL, NULL, 108),
    ('job_title', 'APM', 'مساعد مدير مشروع', 'Assistant project manager', NULL, NULL, 110),
    ('job_title', 'TOM', 'مدير المكتب الفني', 'Technical office manager', NULL, NULL, 112),
    ('job_title', 'CCM', 'مدير التحكم في التكاليف', 'Cost control manager', NULL, NULL, 114),
    ('job_title', 'PLM', 'مدير التخطيط', 'Planning manager', NULL, NULL, 116),
    ('job_title', 'QAM', 'مدير الجودة', 'Quality manager', NULL, NULL, 118),
    ('job_title', 'HSM', 'مدير السلامة والصحة المهنية', 'Health and safety manager', NULL, NULL, 120),
    ('job_title', 'PRM', 'مدير المشتريات', 'Procurement manager', NULL, NULL, 122),
    ('job_title', 'CTM', 'مدير العقود', 'Contracts manager', NULL, NULL, 124),
    ('job_title', 'MEM', 'مدير الأعمال الكهروميكانيكية', 'MEP manager', NULL, NULL, 126),
    ('job_title', 'CVE', 'مهندس مدني', 'Civil engineer', NULL, NULL, 204),
    ('job_title', 'SRE', 'مهندس إنشائي', 'Structural engineer', NULL, NULL, 206),
    ('job_title', 'ARE', 'مهندس معماري', 'Architect', NULL, NULL, 208),
    ('job_title', 'EEN', 'مهندس كهرباء', 'Electrical engineer', NULL, NULL, 210),
    ('job_title', 'MEN', 'مهندس ميكانيكا', 'Mechanical engineer', NULL, NULL, 212),
    ('job_title', 'MPE', 'مهندس أعمال كهروميكانيكية', 'MEP engineer', NULL, NULL, 214),
    ('job_title', 'QSE', 'مهندس حصر وكميات', 'Quantity surveyor', NULL, NULL, 220),
    ('job_title', 'CTE', 'مهندس عقود', 'Contracts engineer', NULL, NULL, 222),
    ('job_title', 'TDE', 'مهندس مناقصات وتسعير', 'Tendering and estimation engineer', NULL, NULL, 224),
    ('job_title', 'TOE', 'مهندس مكتب فني', 'Technical office engineer', NULL, NULL, 226),
    ('job_title', 'SDE', 'مهندس رسومات تنفيذية', 'Shop drawing engineer', NULL, NULL, 228),
    ('job_title', 'BIM', 'مهندس نمذجة معلومات البناء (BIM)', 'BIM engineer', NULL, NULL, 230),
    ('job_title', 'DCE', 'مهندس تصميم', 'Design engineer', NULL, NULL, 232),
    ('job_title', 'QCE', 'مهندس جودة', 'Quality engineer', NULL, NULL, 234),
    ('job_title', 'HSE', 'مهندس سلامة وصحة مهنية', 'Health and safety engineer', NULL, NULL, 236),
    ('job_title', 'FPE', 'مهندس حماية من الحريق', 'Fire protection engineer', NULL, NULL, 238),
    ('job_title', 'GTE', 'مهندس جيوتقني', 'Geotechnical engineer', NULL, NULL, 240),
    ('job_title', 'SVE', 'مهندس مساحة', 'Survey engineer', NULL, NULL, 242),
    ('job_title', 'MTE', 'مهندس مواد ومختبر', 'Materials and laboratory engineer', NULL, NULL, 244),
    ('job_title', 'RDE', 'مهندس طرق', 'Roads engineer', NULL, NULL, 246),
    ('job_title', 'WWE', 'مهندس مياه وصرف صحي', 'Water and wastewater engineer', NULL, NULL, 248),
    ('job_title', 'LSE', 'مهندس تنسيق مواقع', 'Landscape engineer', NULL, NULL, 250),
    ('job_title', 'ENE', 'مهندس بيئة', 'Environmental engineer', NULL, NULL, 252),
    ('job_title', 'MNE', 'مهندس صيانة', 'Maintenance engineer', NULL, NULL, 254),
    ('job_title', 'PRE', 'مهندس مشتريات', 'Procurement engineer', NULL, NULL, 256),
    ('job_title', 'SWE', 'مهندس برمجيات', 'Software engineer', NULL, NULL, 258),
    ('job_title', 'ITE', 'مهندس تقنية معلومات', 'IT engineer', NULL, NULL, 260),
    ('job_title', 'NTE', 'مهندس شبكات واتصالات', 'Network and telecom engineer', NULL, NULL, 262),
    ('job_title', 'SPV', 'مشرف موقع', 'Site supervisor', NULL, NULL, 302),
    ('job_title', 'CVS', 'مشرف أعمال مدنية', 'Civil works supervisor', NULL, NULL, 304),
    ('job_title', 'FNS', 'مشرف تشطيبات', 'Finishing supervisor', NULL, NULL, 306),
    ('job_title', 'ELS', 'مشرف كهرباء', 'Electrical supervisor', NULL, NULL, 308),
    ('job_title', 'MCS', 'مشرف ميكانيكا وسباكة', 'Mechanical and plumbing supervisor', NULL, NULL, 310),
    ('job_title', 'GFM', 'رئيس عمال عام', 'General foreman', NULL, NULL, 312),
    ('job_title', 'QCI', 'مراقب جودة', 'Quality inspector', NULL, NULL, 318),
    ('job_title', 'DCC', 'مراقب وثائق', 'Document controller', NULL, NULL, 402),
    ('job_title', 'DRF', 'رسام هندسي', 'Draftsman', NULL, NULL, 404),
    ('job_title', 'ACC', 'محاسب', 'Accountant', NULL, NULL, 406),
    ('job_title', 'CAC', 'محاسب تكاليف', 'Cost accountant', NULL, NULL, 408),
    ('job_title', 'PRO', 'مسؤول مشتريات', 'Procurement officer', NULL, NULL, 410),
    ('job_title', 'TKP', 'مراقب دوام', 'Timekeeper', NULL, NULL, 414),
    ('job_title', 'HRO', 'مسؤول موارد بشرية', 'Human resources officer', NULL, NULL, 416),
    ('job_title', 'GRO', 'مندوب علاقات حكومية', 'Government relations officer', NULL, NULL, 418),
    ('job_title', 'SCR', 'سكرتير الموقع', 'Site secretary', NULL, NULL, 420),
    ('job_title', 'SVA', 'مساعد مساح', 'Survey assistant', NULL, NULL, 504),
    ('job_title', 'CFT', 'نجار تشطيبات وأبواب', 'Finish carpenter', NULL, NULL, 508),
    ('job_title', 'PLT', 'لياس', 'Plasterer', NULL, NULL, 514),
    ('job_title', 'TLR', 'مبلّط', 'Tile setter', NULL, NULL, 516),
    ('job_title', 'MRB', 'فني رخام وحجر', 'Marble and stone technician', NULL, NULL, 518),
    ('job_title', 'PNT', 'دهّان', 'Painter', NULL, NULL, 520),
    ('job_title', 'GYP', 'فني جبس', 'Gypsum technician', NULL, NULL, 522),
    ('job_title', 'ISL', 'فني عزل', 'Insulation technician', NULL, NULL, 524),
    ('job_title', 'SCF', 'فني سقالات', 'Scaffolder', NULL, NULL, 526),
    ('job_title', 'WLD', 'لحّام', 'Welder', NULL, NULL, 528),
    ('job_title', 'FAB', 'حداد مشغولات معدنية', 'Steel fabricator', NULL, NULL, 530),
    ('job_title', 'ALU', 'فني ألمنيوم وزجاج', 'Aluminium and glazing technician', NULL, NULL, 532),
    ('job_title', 'ACT', 'فني تكييف وتبريد', 'Air conditioning technician', NULL, NULL, 538),
    ('job_title', 'FFT', 'فني أنظمة حريق', 'Fire systems technician', NULL, NULL, 540),
    ('job_title', 'LCT', 'فني تيار خفيف وكاميرات', 'Low current and CCTV technician', NULL, NULL, 542),
    ('job_title', 'ELV', 'فني مصاعد', 'Elevator technician', NULL, NULL, 544),
    ('job_title', 'ITS', 'فني دعم تقني', 'IT support technician', NULL, NULL, 546),
    ('job_title', 'LBT', 'فني مختبر', 'Laboratory technician', NULL, NULL, 548),
    ('job_title', 'MCH', 'ميكانيكي معدات', 'Equipment mechanic', NULL, NULL, 550),
    ('job_title', 'AEL', 'كهربائي معدات', 'Equipment electrician', NULL, NULL, 552),
    ('job_title', 'EXO', 'مشغّل حفار', 'Excavator operator', NULL, NULL, 604),
    ('job_title', 'LDO', 'مشغّل محمّلة', 'Loader operator', NULL, NULL, 606),
    ('job_title', 'CRO', 'مشغّل رافعة', 'Crane operator', NULL, NULL, 608),
    ('job_title', 'RLO', 'مشغّل هراس', 'Roller operator', NULL, NULL, 610),
    ('job_title', 'PMO', 'مشغّل مضخة خرسانة', 'Concrete pump operator', NULL, NULL, 612),
    ('job_title', 'FLO', 'مشغّل رافعة شوكية', 'Forklift operator', NULL, NULL, 614),
    ('job_title', 'HDV', 'سائق شاحنة ثقيلة', 'Heavy truck driver', NULL, NULL, 618),
    ('job_title', 'MXD', 'سائق خلاطة خرسانة', 'Mixer truck driver', NULL, NULL, 620),
    ('job_title', 'HLP', 'مساعد فني', 'Technician helper', NULL, NULL, 704),
    ('job_title', 'CLN', 'عامل نظافة', 'Cleaner', NULL, NULL, 706),
    ('job_title', 'SGD', 'حارس أمن', 'Security guard', NULL, NULL, 708),
    ('job_title', 'MSG', 'مراسل', 'Office messenger', NULL, NULL, 710),
    ('job_title', 'CHF', 'طبّاخ', 'Cook', NULL, NULL, 712)
ON CONFLICT (kind, code) DO NOTHING;

UPDATE catalog_items SET sort = 106 WHERE kind = 'job_title' AND code = 'PJM';
UPDATE catalog_items SET sort = 202 WHERE kind = 'job_title' AND code = 'STE';
UPDATE catalog_items SET sort = 216 WHERE kind = 'job_title' AND code = 'PLE';
UPDATE catalog_items SET sort = 218 WHERE kind = 'job_title' AND code = 'CCE';
UPDATE catalog_items SET sort = 314 WHERE kind = 'job_title' AND code = 'FRM';
UPDATE catalog_items SET sort = 316 WHERE kind = 'job_title' AND code = 'INS';
UPDATE catalog_items SET sort = 320 WHERE kind = 'job_title' AND code = 'SAF';
UPDATE catalog_items SET sort = 412 WHERE kind = 'job_title' AND code = 'STK';
UPDATE catalog_items SET sort = 502 WHERE kind = 'job_title' AND code = 'SRV';
UPDATE catalog_items SET sort = 506 WHERE kind = 'job_title' AND code = 'CRP';
UPDATE catalog_items SET sort = 510 WHERE kind = 'job_title' AND code = 'SFX';
UPDATE catalog_items SET sort = 512 WHERE kind = 'job_title' AND code = 'MSN';
UPDATE catalog_items SET sort = 534 WHERE kind = 'job_title' AND code = 'ELC';
UPDATE catalog_items SET sort = 536 WHERE kind = 'job_title' AND code = 'PLB';
UPDATE catalog_items SET sort = 602 WHERE kind = 'job_title' AND code = 'EQO';
UPDATE catalog_items SET sort = 616 WHERE kind = 'job_title' AND code = 'DRV';
UPDATE catalog_items SET sort = 702 WHERE kind = 'job_title' AND code = 'LBR';

DO $$
DECLARE t record;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t.tablename);
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated', t.tablename);
        END IF;
    END LOOP;
END $$;
