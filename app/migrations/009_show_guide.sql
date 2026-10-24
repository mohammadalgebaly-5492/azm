-- تفضيل شخصي: عرض الشروح تحت العناوين والحقول (يُحفظ مع الحساب فيعمل على كل الأجهزة)
ALTER TABLE users ADD COLUMN show_guide INTEGER NOT NULL DEFAULT 0;
