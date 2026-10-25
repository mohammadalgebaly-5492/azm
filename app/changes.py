"""طلبات التغيير (الدستور، البند 4.9): مهندس المشروع يرفع، ومدير المشروع يراجع، ومهندس تحكم تكلفة يدرس الأثر ويعتمد الداخلي حتى
10,000 ريال، والمدير التنفيذي يعتمد ما فوقه والتعاقدي دائمًا. الداخلي المعتمد يعدّل ميزانية البنود، والتعاقدي يصبح أمر تغيير."""
from datetime import date

from . import audit
from .contracts import add_variation_order, contract_of
from .db import next_counter, tx, utcnow
from .errors import AuthError
from .i18n import _
from .procurement import LIMIT

KINDS = {"internal": "Internal change", "contractual": "Contractual change"}
SOURCES = {"company": "The company", "owner": "Owner", "consultant": "Consultant"}
STATUS = {"pm_review": "Waiting for the project manager", "cc_review": "Waiting for cost control",
          "dir_review": "Waiting for the Director", "approved": "Approved", "returned": "Returned"}


def _signed(raw):
    s = str(raw or "").strip().replace(",", "").replace("٬", "")
    if not s:
        return 0
    neg = s.startswith("-")
    from .projects import parse_money
    v = parse_money(s.lstrip("-+"))
    return -(v or 0) if neg else (v or 0)


def requests(db, pid):
    return db.execute("SELECT r.*, v.code AS vo_code FROM change_requests r LEFT JOIN variation_orders v ON v.id = r.vo_id "
                      "WHERE r.project_id = ? ORDER BY r.id DESC", (pid,)).fetchall()


def items_of(db, cr_id):
    return db.execute("SELECT x.*, b.code, b.description FROM cr_items x JOIN boq_items b ON b.id = x.boq_item_id "
                      "WHERE x.cr_id = ? ORDER BY b.code", (cr_id,)).fetchall()


def create(db, pid, form, actor_id) -> str:
    from .authority import ensure_can_raise
    ensure_can_raise(db, actor_id)
    kind, source = form.get("kind") or "", form.get("source") or ""
    if kind not in KINDS:
        raise AuthError(_("Choose the type of change."))
    if source not in SOURCES:
        raise AuthError(_("Choose the source of the change."))
    desc = (form.get("description") or "").strip()
    if len(desc) < 10:
        raise AuthError(_("Describe the change and its reason."))
    getlist = form.getlist if hasattr(form, "getlist") else (lambda k: form.get(k) or [])
    valid = {r[0] for r in db.execute("SELECT id FROM boq_items WHERE project_id = ?", (pid,))}
    items = sorted({int(x) for x in getlist("items") if str(x).isdigit() and int(x) in valid})
    if not items:
        raise AuthError(_("Choose the affected items."))
    amounts = {i: _signed(form.get(f"amount_{i}")) for i in items}
    cost = sum(amounts.values())
    try:
        days = int(str(form.get("days_impact") or "0").strip())
    except ValueError:
        raise AuthError(_("Enter the effect on the duration as a whole number of days."))
    if kind == "contractual" and cost == 0 and days == 0:
        raise AuthError(_("A change order must change the value or the duration."))
    acts = sorted({int(x) for x in getlist("activities") if str(x).isdigit()} &
                  {r[0] for r in db.execute("SELECT id FROM activities WHERE project_id = ?", (pid,))})
    p = db.execute("SELECT code FROM projects WHERE id = ?", (pid,)).fetchone()
    counter = "cr-%d" % pid
    with tx(db):
        code = f"{p['code']}-CR-{next_counter(db, counter):03d}"
        cid = db.execute("INSERT INTO change_requests(project_id, code, kind, source, description, cost_impact, days_impact, "
                         "resource_impact, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?,?) RETURNING id",
                         (pid, code, kind, source, desc, cost, days, (form.get("resource_impact") or "").strip() or None,
                          utcnow(), actor_id)).fetchone()[0]
        for i in items:
            db.execute("INSERT INTO cr_items(cr_id, boq_item_id, amount) VALUES (?, ?, ?)", (cid, i, amounts[i]))
        for a in acts:
            db.execute("INSERT INTO cr_activities(cr_id, activity_id) VALUES (?, ?)", (cid, a))
        audit.log(db, actor_id, "cr_raised", "project", pid, pid, code=code, amount=cost, days=days)
    return code


def _cr(db, pid, cid):
    r = db.execute("SELECT * FROM change_requests WHERE id = ? AND project_id = ?", (cid, pid)).fetchone()
    if r is None:
        raise AuthError(_("This change request doesn't exist."))
    return r


def advance(db, pid, cid, actor_id, role):
    """role: pm (مراجعة مدير المشروع)، أو cc (دراسة الأثر)، أو director."""
    r = _cr(db, pid, cid)
    expected = {"pm": "pm_review", "cc": "cc_review", "director": "dir_review"}[role]
    if r["status"] != expected:
        raise AuthError(_("This change request is not at this step."))
    if actor_id in (r["created_by"], r["pm_by"], r["cc_by"]):
        raise AuthError(_("Whoever raised or approved a step can't approve the next one."))
    if role == "pm":
        with tx(db):
            db.execute("UPDATE change_requests SET status = 'cc_review', pm_at = ?, pm_by = ? WHERE id = ?", (utcnow(), actor_id, cid))
            audit.log(db, actor_id, "cr_reviewed", "project", pid, pid, code=r["code"])
        return
    final = role == "director" or (r["kind"] == "internal" and abs(r["cost_impact"]) <= LIMIT)
    if final and r["kind"] == "contractual":
        c = contract_of(db, pid)
        if c is None:
            raise AuthError(_("Record the main contract first."))
        vid, _code = add_variation_order(db, c["id"], {"description": r["description"], "issued_on": date.today().isoformat(),
                                                        "value_delta": f"{r['cost_impact'] / 100:.2f}",
                                                        "days_delta": str(r["days_impact"]),
                                                        "items": [str(x["boq_item_id"]) for x in items_of(db, cid)]}, actor_id)
    else:
        vid = None
    sets = ("status = ?, dir_at = ?, dir_by = ?" if role == "director" else "status = ?, cc_at = ?, cc_by = ?")
    with tx(db):
        db.execute(f"UPDATE change_requests SET {sets}, vo_id = ? WHERE id = ?",
                   ("approved" if final else "dir_review", utcnow(), actor_id, vid, cid))
        if final and r["kind"] == "internal":
            for x in items_of(db, cid):
                if x["amount"]:
                    db.execute("INSERT INTO budget_adjustments(project_id, boq_item_id, cr_id, amount, created_at) VALUES (?,?,?,?,?)",
                               (pid, x["boq_item_id"], cid, x["amount"], utcnow()))
        audit.log(db, actor_id, "cr_approved" if final else "cr_studied", "project", pid, pid, code=r["code"])


def send_back(db, pid, cid, reason, actor_id):
    r = _cr(db, pid, cid)
    if r["status"] not in ("pm_review", "cc_review", "dir_review"):
        raise AuthError(_("This change request is not waiting for a decision."))
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise AuthError(_("Write the reason for returning."))
    with tx(db):
        db.execute("UPDATE change_requests SET status = 'returned', return_reason = ? WHERE id = ?", (reason, cid))
        audit.log(db, actor_id, "cr_returned", "project", pid, pid, code=r["code"], reason=reason)


def adjustments(db, item_id) -> int:
    return db.execute("SELECT CAST(COALESCE(SUM(amount), 0) AS BIGINT) FROM budget_adjustments WHERE boq_item_id = ?",
                      (item_id,)).fetchone()[0]
