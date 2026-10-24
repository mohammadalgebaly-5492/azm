-- صلاحية صفحة التحليلات: تُمنح افتراضيًا للكوست كنترول والدايركتور والمشاهد، ويعدّلها مدير النظام من شاشة الأدوار
INSERT INTO role_permissions(role, permission)
SELECT key, 'analytics.view' FROM roles WHERE key IN ('admin', 'director', 'viewer')
ON CONFLICT DO NOTHING;
