-- مسميات الأدوار الجاهزة تصبح كما في دستور المنصة (المادة 1). تتغير الأسماء فقط، ولا يُمسّ دور غيّر المدير اسمه بنفسه.
UPDATE roles SET name_ar = 'مهندس تحكم تكلفة', name_en = 'Cost Control Engineer'
    WHERE key = 'admin' AND name_ar = 'الكوست كنترول (المسؤول)' AND name_en = 'Cost Control (Admin)';
UPDATE roles SET name_ar = 'المدير التنفيذي'
    WHERE key = 'director' AND name_ar = 'الدايركتور';
UPDATE roles SET name_ar = 'المحاسبة', name_en = 'Accounting'
    WHERE key = 'accountant' AND name_ar = 'المحاسب' AND name_en = 'Accountant';
UPDATE roles SET name_ar = 'المشاهد', name_en = 'Viewer'
    WHERE key = 'viewer' AND name_ar = 'مشاهد (الإدارة العليا)' AND name_en = 'Viewer (Senior Management)';
