import json

from flask import has_request_context, request

from .db import utcnow


def log(db, actor_id, action, entity=None, entity_id=None, project_id=None, **details):
    ip = request.remote_addr if has_request_context() else None
    db.execute(
        "INSERT INTO audit_log(at, actor_id, action, entity, entity_id, project_id, details, ip) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (utcnow(), actor_id, action, entity, entity_id, project_id,
         json.dumps(details, ensure_ascii=False) if details else None, ip),
    )


ACTION_LABELS = {
    "login": "تسجيل دخول",
    "login_failed": "محاولة دخول فاشلة",
    "account_locked": "قفل الحساب بعد محاولات فاشلة",
    "logout": "تسجيل خروج",
    "password_changed": "تغيير كلمة المرور",
    "user_created": "إنشاء حساب",
    "user_updated": "تعديل حساب",
    "password_reset": "إعادة تعيين كلمة المرور",
    "user_disabled": "إيقاف حساب",
    "user_enabled": "إعادة تفعيل حساب",
    "project_created": "إنشاء مشروع",
    "project_updated": "تعديل بيانات مشروع",
    "member_added": "إسناد عضو للمشروع",
    "member_removed": "إزالة عضو من المشروع",
    "wbs_added": "إضافة عنصر WBS",
    "wbs_renamed": "تعديل اسم عنصر WBS",
    "wbs_deleted": "حذف عنصر WBS",
    "boq_item_added": "إضافة بند لجدول الكميات",
    "boq_item_updated": "تعديل بند في جدول الكميات",
    "boq_item_deleted": "حذف بند من جدول الكميات",
    "boq_imported": "استيراد جدول الكميات من Excel",
    "baseline_approved": "اعتماد الميزانية الأصلية وتجميدها",
}
