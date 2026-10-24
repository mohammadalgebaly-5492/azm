-- الأدوار تصبح بيانات يديرها مدير النظام: إنشاء، إعادة تسمية، صلاحيات، حذف.
-- دور مدير النظام (system) ثابت ولا يُعدّل ولا يُحذف، حتى لا تفقد المنصة من يديرها.

CREATE TABLE roles (
    key         TEXT PRIMARY KEY,
    code        TEXT NOT NULL UNIQUE CHECK (code ~ '^[A-Z]{2,5}$'),   -- يدخل في كود الحساب: USR-PM-03
    name_ar     TEXT NOT NULL,
    name_en     TEXT NOT NULL,
    external    BOOLEAN NOT NULL DEFAULT FALSE,                       -- طرف خارجي (المالك، الاستشاري...)
    system      BOOLEAN NOT NULL DEFAULT FALSE,
    sort        INTEGER NOT NULL DEFAULT 100,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO roles(key, code, name_ar, name_en, external, system, sort) VALUES
    ('superadmin', 'SYS', 'مدير النظام', 'System Owner', FALSE, TRUE, 0),
    ('admin', 'ADM', 'الكوست كنترول (المسؤول)', 'Cost Control (Admin)', FALSE, FALSE, 10),
    ('pm', 'PM', 'مدير المشروع', 'Project Manager', FALSE, FALSE, 20),
    ('director', 'DIR', 'الدايركتور', 'Director', FALSE, FALSE, 30),
    ('accountant', 'ACC', 'المحاسب', 'Accountant', FALSE, FALSE, 40),
    ('viewer', 'VWR', 'مشاهد (الإدارة العليا)', 'Viewer (Senior Management)', FALSE, FALSE, 50),
    ('owner_rep', 'OWN', 'ممثل المالك', 'Owner''s Representative', TRUE, FALSE, 60),
    ('consultant', 'CON', 'الاستشاري', 'Consultant', TRUE, FALSE, 70);

ALTER TABLE users DROP CONSTRAINT users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_fkey FOREIGN KEY (role) REFERENCES roles(key);
DELETE FROM role_permissions WHERE role NOT IN (SELECT key FROM roles);
ALTER TABLE role_permissions ADD CONSTRAINT role_permissions_role_fkey FOREIGN KEY (role) REFERENCES roles(key) ON DELETE CASCADE;

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
