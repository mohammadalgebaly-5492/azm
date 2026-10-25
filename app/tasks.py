"""صفحة «مهامي» (الدستور، المادة 4، مبدأ الحوكمة 6): ما ينتظر المستخدم في كل مشاريعه، حسب صلاحياته، مع التنبيه على ما تأخر
أكثر من 3 أيام (البند 4.11). لا يظهر للمستخدم ما أعدّه أو اعتمده بنفسه في خطوة سابقة."""
from datetime import date

from flask import url_for

from .i18n import _
from .rbac import can, can_view_project

LATE_DAYS = 3
_SIGNED = ("SELECT COALESCE(c.code, x.code) AS code, s.uploaded_at, s.cc_at FROM signed_copies s "
           "LEFT JOIN commitments c ON s.doc_kind = 'commitment' AND c.id = s.doc_id "
           "LEFT JOIN payables x ON s.doc_kind = 'payable' AND x.id = s.doc_id WHERE s.project_id = ? ")


def _age(v):
    try:
        return (date.today() - date.fromisoformat(str(v)[:10])).days
    except (TypeError, ValueError):
        return 0


def collect(db, user) -> list[dict]:
    projects = [p for p in db.execute("SELECT id, code, name FROM projects WHERE status != 'closed' ORDER BY code").fetchall()
                if can_view_project(db, user, p["id"])]
    me, out = user["id"], []

    def add(p, what, code, link, since):
        out.append({"project": p, "what": what, "code": code, "link": link, "age": _age(since)})

    for p in projects:
        pid = p["id"]
        if can(user, "changes.approve"):
            for a in db.execute("SELECT id, code, created_at FROM allocations WHERE project_id = ? AND status = 'planned' "
                                "AND created_by != ?", (pid, me)):
                add(p, _("Approve a resource allocation"), a["code"], url_for("resources.project", pid=pid) + "#allocations",
                    a["created_at"])
            st = db.execute("SELECT schedule_reviewed_at, schedule_reviewed_by, schedule_approved_at FROM projects WHERE id = ?",
                            (pid,)).fetchone()
            if st["schedule_reviewed_at"] and not st["schedule_approved_at"] and st["schedule_reviewed_by"] != me:
                add(p, _("Approve the schedule as the time baseline"), p["code"], url_for("schedule.page", pid=pid),
                    st["schedule_reviewed_at"])
            for r in db.execute("SELECT id, code, cc_at FROM purchase_requests WHERE project_id = ? AND status = 'cc_approved' "
                                "AND ? NOT IN (created_by, selected_by, cc_by)", (pid, me)):
                add(p, _("Approve a purchase above 10,000 SAR"), r["code"], url_for("procurement.view", pid=pid, rid=r["id"]), r["cc_at"])
            for x in db.execute("SELECT code, cc_at FROM payables WHERE project_id = ? AND status = 'cc_approved' "
                                "AND ? NOT IN (created_by, cc_by)", (pid, me)):
                add(p, _("Approve a certificate or invoice above 10,000 SAR"), x["code"], url_for("payables.page", pid=pid), x["cc_at"])
            for r in db.execute("SELECT code, cc_at FROM change_requests WHERE project_id = ? AND status = 'dir_review' "
                                "AND ? NOT IN (created_by, pm_by, cc_by)", (pid, me)):
                add(p, _("Approve a change request"), r["code"], url_for("changes.page", pid=pid), r["cc_at"])
            for v in db.execute("SELECT v.code, v.created_at FROM variation_orders v JOIN contracts c ON c.id = v.contract_id "
                                "WHERE c.project_id = ? AND v.status = 'study' AND v.created_by != ?", (pid, me)):
                add(p, _("Decide a change order on the main contract"), v["code"], url_for("contracts.page", pid=pid) + "#variations",
                    v["created_at"])
        if can(user, "projects.manage"):
            for r in db.execute("SELECT id, code, created_at FROM daily_reports WHERE project_id = ? AND status = 'review' "
                                "AND created_by != ?", (pid, me)):
                add(p, _("Review a daily site report"), r["code"], url_for("daily.view", pid=pid, rid=r["id"]), r["created_at"])
            for d in db.execute("SELECT id, code, created_at FROM documents WHERE project_id = ? AND reviewed_at IS NULL "
                                "AND created_by != ?", (pid, me)):
                add(p, _("Review the data of a document"), d["code"], url_for("documents.view", pid=pid, did=d["id"]), d["created_at"])
            for r in db.execute("SELECT code, pm_at FROM change_requests WHERE project_id = ? AND status = 'cc_review' "
                                "AND ? NOT IN (created_by, pm_by)", (pid, me)):
                add(p, _("Study the impact of a change request"), r["code"], url_for("changes.page", pid=pid), r["pm_at"])
            for o in db.execute("SELECT code, created_at FROM owner_certificates WHERE project_id = ? AND status = 'draft' "
                                "AND created_by != ?", (pid, me)):
                add(p, _("Agree to an owner certificate"), o["code"], url_for("payables.billing", pid=pid), o["created_at"])
        if can(user, "procurement.approve"):
            for r in db.execute("SELECT id, code, selected_at FROM purchase_requests WHERE project_id = ? AND status = 'selected' "
                                "AND ? NOT IN (created_by, selected_by)", (pid, me)):
                add(p, _("Approve a chosen quote"), r["code"], url_for("procurement.view", pid=pid, rid=r["id"]), r["selected_at"])
        if can(user, "procurement.quotes"):
            for r in db.execute("SELECT id, code, created_at FROM purchase_requests WHERE project_id = ? AND status IN "
                                "('quoting','returned') AND (SELECT COUNT(*) FROM quotes q WHERE q.request_id = purchase_requests.id) < 2",
                                (pid,)):
                add(p, _("Collect quotes for a request"), r["code"], url_for("procurement.view", pid=pid, rid=r["id"]), r["created_at"])
        if can(user, "procurement.select"):
            for r in db.execute("SELECT id, code, created_at FROM purchase_requests WHERE project_id = ? AND status IN "
                                "('quoting','returned') AND created_by != ? AND (SELECT COUNT(*) FROM quotes q "
                                "WHERE q.request_id = purchase_requests.id) >= 2", (pid, me)):
                add(p, _("Choose a quote"), r["code"], url_for("procurement.view", pid=pid, rid=r["id"]), r["created_at"])
        if can(user, "payables.approve"):
            for x in db.execute("SELECT code, created_at FROM payables WHERE project_id = ? AND status = 'review' AND created_by != ?",
                                (pid, me)):
                add(p, _("Approve a certificate or invoice"), x["code"], url_for("payables.page", pid=pid), x["created_at"])
        if can(user, "payables.approve"):
            for s in db.execute(_SIGNED + "AND s.status = 'review' AND s.uploaded_by != ?", (pid, me)):
                add(p, _("Accept a signed copy"), s["code"], url_for("payables.page", pid=pid), s["uploaded_at"])
        if can(user, "changes.approve"):
            for s in db.execute(_SIGNED + "AND s.status = 'cc_ok' AND ? NOT IN (s.uploaded_by, s.cc_by)", (pid, me)):
                add(p, _("Accept a signed copy above 10,000 SAR"), s["code"], url_for("payables.page", pid=pid), s["cc_at"])
        if can(user, "payables.pay"):
            for x in db.execute("SELECT code, COALESCE(dir_at, cc_at) AS since FROM payables WHERE project_id = ? "
                                "AND status = 'approved' AND ? NOT IN (created_by, cc_by) AND (dir_by IS NULL OR dir_by != ?)",
                                (pid, me, me)):
                add(p, _("Pay an approved certificate or invoice"), x["code"], url_for("payables.page", pid=pid), x["since"])
        if can(user, "changes.request"):
            for r in db.execute("SELECT code, created_at FROM change_requests WHERE project_id = ? AND status = 'pm_review' "
                                "AND created_by != ?", (pid, me)):
                add(p, _("Review a change request"), r["code"], url_for("changes.page", pid=pid), r["created_at"])
        if can(user, "projects.manage"):
            for x in db.execute("SELECT code, created_at FROM recovery_plans WHERE project_id = ? AND status = 'review' "
                                "AND created_by != ?", (pid, me)):
                add(p, _("Review a recovery plan"), x["code"], url_for("governance.control", pid=pid) + "#plans", x["created_at"])
        if can(user, "changes.approve"):
            for x in db.execute("SELECT code, cc_at FROM recovery_plans WHERE project_id = ? AND status = 'cc_reviewed' "
                                "AND ? NOT IN (created_by, cc_by)", (pid, me)):
                add(p, _("Approve a recovery plan"), x["code"], url_for("governance.control", pid=pid) + "#plans", x["cc_at"])
        if can(user, "project.lead"):
            for r in db.execute("SELECT id, code, created_at FROM daily_reports WHERE project_id = ? AND status = 'review' "
                                "AND needs_pm = ? AND pm_checked_at IS NULL AND created_by != ?", (pid, True, me)):
                add(p, _("Check a daily report of a restricted engineer"), r["code"], url_for("daily.view", pid=pid, rid=r["id"]),
                    r["created_at"])
        if can(user, "schedule.manage"):
            for r in db.execute("SELECT id, code, reviewed_at FROM daily_reports WHERE project_id = ? AND status = 'returned' "
                                "AND created_by = ?", (pid, me)):
                add(p, _("Fix and resubmit a returned daily report"), r["code"], url_for("daily.form", pid=pid, rid=r["id"]),
                    r["reviewed_at"])
    if can(user, "changes.approve"):
        from .authority import recent_changes
        for c in recent_changes(db):
            out.append({"project": {"name": c["full_name"], "code": "—"}, "what": _("Note an authority change"),
                        "code": c["to_level"], "link": url_for("daily.engineers"), "age": _age(c["set_at"])})
    return sorted(out, key=lambda t: -t["age"])
