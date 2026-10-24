-- دور مدير النظام (System Owner) فوق الكوست كنترول، وجدول إعدادات المنصة، ومصفوفة صلاحيات الأدوار

ALTER TABLE users DROP CONSTRAINT users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN
    ('superadmin','admin','pm','director','accountant','viewer','owner_rep','consultant'));

CREATE TABLE settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL,
    updated_by  BIGINT REFERENCES users(id)
);

-- صلاحيات كل دور يعدّلها مدير النظام من الواجهة. مدير النظام نفسه له كل الصلاحيات دائمًا ولا يُسجل هنا
CREATE TABLE role_permissions (
    role        TEXT NOT NULL,
    permission  TEXT NOT NULL,
    PRIMARY KEY (role, permission)
);
INSERT INTO role_permissions(role, permission) VALUES
    ('admin', 'users.manage'),
    ('admin', 'projects.create'),
    ('admin', 'projects.manage'),
    ('admin', 'projects.view_all'),
    ('admin', 'audit.view'),
    ('admin', 'boq.manage'),
    ('director', 'projects.view_all'),
    ('viewer', 'projects.view_all');

-- كل منصة لازم يكون فيها مدير نظام: أقدم أدمن فعّال يُرقّى تلقائيًا، ويُسجل ذلك في السجل
WITH promoted AS (
    UPDATE users SET role = 'superadmin'
    WHERE id = (SELECT id FROM users WHERE role = 'admin' AND status = 'active' ORDER BY id LIMIT 1)
      AND NOT EXISTS (SELECT 1 FROM users WHERE role = 'superadmin')
    RETURNING id
)
INSERT INTO audit_log(at, actor_id, action, entity, entity_id, details)
SELECT now(), NULL, 'user_updated', 'user', id,
       '{"role": {"from": "admin", "to": "superadmin"}, "reason": "system owner role introduced"}'::jsonb
FROM promoted;

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
