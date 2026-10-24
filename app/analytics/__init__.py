"""التحليلات: كل بطاقة وحدة مستقلة في ملف خاص بها.

لإضافة تحليلات لميزة جديدة: أنشئ ملفًا هنا يعرّف KEY و TITLE و PERMISSION و SIZE ودالة data()،
وقالبًا في templates/analytics/<KEY>.html، ثم أضف الوحدة إلى WIDGETS. لا شيء غير ذلك يتغير.
كل بطاقة تُحسب منفصلة: لو فشلت واحدة تظهر «غير متاحة» وتبقى البقية سليمة.
"""
import logging

from flask import render_template

from ..rbac import can
from . import accounts_by_role, boq_coverage, boq_types, contract_by_project, projects_overview, signin_activity

WIDGETS = [projects_overview, contract_by_project, boq_coverage, boq_types, accounts_by_role, signin_activity]
log = logging.getLogger(__name__)


def render_all(db, user, scope):
    """scope: المشروعات المرئية للمستخدم (يحسبها مرة واحدة الصفحة، وكل بطاقة تقرأ منها فقط)."""
    out = []
    for w in WIDGETS:
        if w.PERMISSION and not can(user, w.PERMISSION):
            continue
        try:
            html = render_template(f"analytics/{w.KEY}.html", d=w.data(db, user, scope), w=w)
        except Exception:
            log.exception("analytics widget %s failed", w.KEY)
            html = render_template("analytics/_unavailable.html", w=w)
        out.append((w, html))
    return out
