"""المشتريات والتعاقد مع مقاولي الباطن والموردين (الدستور، البند 4.2): الطلب، وعروض الأسعار (عرضان على الأقل)، واختيار
مدير المشروع، واعتماد مهندس تحكم تكلفة ثم المدير التنفيذي فوق الحد، والالتزام على ميزانية البند. من يُعِد لا يعتمد."""
from datetime import date, timedelta

from . import audit
from .boq import parse_qty
from .db import next_counter, tx, utcnow
from .errors import AuthError
from .i18n import _
from .projects import fmt_money, parse_money
from .resources import _date

KINDS = {"material": "Purchase of materials", "subcontract": "Subcontract", "rental": "Equipment rental"}
STATUS = {"quoting": "Collecting quotes", "selected": "Waiting for cost control", "cc_approved": "Waiting for the Director",
          "approved": "Approved", "returned": "Returned", "cancelled": "Cancelled"}
EVALUATION = {"compliant": "Compliant", "notes": "Compliant with comments", "non_compliant": "Not compliant"}
LIMIT = 1000000                 # 10,000 ريال: حد مهندس تحكم تكلفة وحده (قرار م. محمد)
SPLIT_DAYS = 30                 # منع التجزئة: نفس البند ونفس الجهة خلال 30 يومًا
MIN_QUOTES = 2
OPEN = ("quoting", "returned")


def requests(db, pid):
    return db.execute(
        "SELECT r.*, b.code AS item_code, b.description AS item_desc, q.total AS selected_total, e.name AS selected_name, "
        "(SELECT COUNT(*) FROM quotes x WHERE x.request_id = r.id) AS n_quotes, c.code AS order_code "
        "FROM purchase_requests r JOIN boq_items b ON b.id = r.boq_item_id LEFT JOIN quotes q ON q.id = r.selected_quote_id "
        "LEFT JOIN entities e ON e.id = q.entity_id LEFT JOIN commitments c ON c.request_id = r.id "
        "WHERE r.project_id = ? ORDER BY r.id DESC", (pid,)).fetchall()


def request(db, pid, rid):
    return db.execute("SELECT r.*, b.code AS item_code, b.description AS item_desc, b.amount AS item_amount "
                      "FROM purchase_requests r JOIN boq_items b ON b.id = r.boq_item_id WHERE r.id = ? AND r.project_id = ?",
                      (rid, pid)).fetchone()


def quotes(db, rid):
    return db.execute("SELECT q.*, e.name AS entity_name, e.code AS entity_code FROM quotes q JOIN entities e ON e.id = q.entity_id "
                      "WHERE q.request_id = ? ORDER BY q.total, q.id", (rid,)).fetchall()


def commitments(db, pid):
    return db.execute("SELECT c.*, e.name AS entity_name, b.code AS item_code, b.description AS item_desc FROM commitments c "
                      "JOIN entities e ON e.id = c.entity_id JOIN boq_items b ON b.id = c.boq_item_id "
                      "WHERE c.project_id = ? ORDER BY c.id", (pid,)).fetchall()


def committed(db, item_id) -> int:
    return db.execute("SELECT CAST(COALESCE(SUM(total), 0) AS BIGINT) FROM commitments WHERE boq_item_id = ?",
                      (item_id,)).fetchone()[0]


def available(db, item_id) -> int:
    """الميزانية المتاحة للبند: ميزانيته ناقص الالتزامات المعتمدة (لا التزام بدون ميزانية)."""
    amount = db.execute("SELECT amount FROM boq_items WHERE id = ?", (item_id,)).fetchone()[0]
    return amount - committed(db, item_id)


def suggested_date(db, pid, item_id):
    """التاريخ المطلوب تقترحه المنصة من الجدول الزمني: أقرب بدء مخطط لنشاط البند."""
    r = db.execute("SELECT MIN(planned_start) FROM activities WHERE project_id = ? AND boq_item_id = ?", (pid, item_id)).fetchone()
    return str(r[0])[:10] if r and r[0] else None


def _ids(form, key, valid):
    getlist = form.getlist if hasattr(form, "getlist") else (lambda k: form.get(k) or [])
    return sorted({int(x) for x in getlist(key) if str(x).isdigit() and int(x) in valid})


def create_request(db, pid, form, actor_id) -> tuple[int, str]:
    p = db.execute("SELECT code FROM projects WHERE id = ?", (pid,)).fetchone()
    kind = form.get("kind") or ""
    if kind not in KINDS:
        raise AuthError(_("Choose the request type."))
    raw = str(form.get("boq_item_id") or "")
    item = db.execute("SELECT * FROM boq_items WHERE id = ? AND project_id = ?", (int(raw), pid)).fetchone() if raw.isdigit() else None
    if item is None:
        raise AuthError(_("Choose the BOQ item."))
    scope = (form.get("scope") or "").strip()
    if len(scope) < 10:
        raise AuthError(_("Describe the required scope of work."))
    qty = parse_qty(form.get("qty"))
    if qty <= 0:
        raise AuthError(_("Enter the quantity."))
    unit = (form.get("unit") or item["unit"]).strip()
    needed = _date(form.get("needed_on"), _("the required date"))
    steps = _ids(form, "steps", {r[0] for r in db.execute("SELECT id FROM scope_steps WHERE boq_item_id = ?", (item["id"],))})
    has_steps = db.execute("SELECT 1 FROM scope_steps WHERE boq_item_id = ?", (item["id"],)).fetchone()
    if has_steps and not steps:
        raise AuthError(_("Choose the scope steps covered by this request."))
    docs = _ids(form, "documents", {r[0] for r in db.execute("SELECT id FROM documents WHERE project_id = ?", (pid,))})
    if not docs:
        raise AuthError(_("Attach at least one drawing or specification from the project documents."))
    counter = "pr-%d" % pid
    with tx(db):
        code = f"{p['code']}-PR-{next_counter(db, counter):04d}"
        rid = db.execute("INSERT INTO purchase_requests(project_id, code, kind, boq_item_id, scope, qty_milli, unit, needed_on, "
                         "created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?,?) RETURNING id",
                         (pid, code, kind, item["id"], scope, qty, unit, needed, utcnow(), actor_id)).fetchone()[0]
        for s in steps:
            db.execute("INSERT INTO pr_steps(request_id, step_id) VALUES (?, ?)", (rid, s))
        for d in docs:
            db.execute("INSERT INTO pr_documents(request_id, document_id) VALUES (?, ?)", (rid, d))
        audit.log(db, actor_id, "pr_created", "project", pid, pid, code=code, kind=kind)
    return rid, code


def _open(db, pid, rid):
    r = request(db, pid, rid)
    if r is None:
        raise AuthError(_("This request doesn't exist."))
    return r


def add_quote(db, pid, rid, form, actor_id) -> str:
    r = _open(db, pid, rid)
    if r["status"] not in OPEN:
        raise AuthError(_("Quotes are added while the request is collecting quotes."))
    want = "subcontractor" if r["kind"] == "subcontract" else "supplier"
    raw = str(form.get("entity_id") or "")
    ent = db.execute("SELECT * FROM entities WHERE id = ?", (int(raw),)).fetchone() if raw.isdigit() else None
    if ent is None or ent["kind"] != want or ent["approval_status"] != "approved" or not ent["active"]:
        raise AuthError(_("Choose an approved subcontractor.") if want == "subcontractor" else _("Choose an approved supplier."))
    if db.execute("SELECT 1 FROM quotes WHERE request_id = ? AND entity_id = ?", (rid, ent["id"])).fetchone():
        raise AuthError(_("This entity already has a quote on this request."))
    price = parse_money(form.get("unit_price"))
    if price is None:
        raise AuthError(_("Enter the unit price."))
    try:
        days = int(form.get("duration_days") or 0)
    except ValueError:
        days = 0
    if days < 1:
        raise AuthError(_("Enter the supply or execution period in days."))
    terms = (form.get("payment_terms") or "").strip()
    if len(terms) < 3:
        raise AuthError(_("Write the payment terms."))
    valid = _date(form.get("valid_until"), _("the validity date"))
    if valid < date.today().isoformat():
        raise AuthError(_("This quote has expired."))
    ev = form.get("evaluation") or ""
    if ev not in EVALUATION:
        raise AuthError(_("Choose the technical evaluation."))
    total = (r["qty_milli"] * price + 500) // 1000
    p = db.execute("SELECT code FROM projects WHERE id = ?", (pid,)).fetchone()
    counter = "qt-%d" % pid
    with tx(db):
        code = f"{p['code']}-QT-{next_counter(db, counter):04d}"
        db.execute("INSERT INTO quotes(request_id, code, entity_id, unit_price, total, duration_days, payment_terms, valid_until, "
                   "evaluation, notes, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (rid, code, ent["id"], price, total, days, terms, valid, ev, (form.get("notes") or "").strip() or None,
                    utcnow(), actor_id))
        audit.log(db, actor_id, "quote_added", "project", pid, pid, code=code, amount=total)
    return code


def comparison(db, r) -> dict:
    """جدول المقارنة: لكل عرض السعر والفرق عن الميزانية المتاحة والمدة والتقييم، والأقل سعرًا من المطابقة."""
    qs = quotes(db, r["id"])
    avail = available(db, r["boq_item_id"])
    eligible = [q for q in qs if q["evaluation"] != "non_compliant"]
    lowest = min(eligible, key=lambda q: q["total"])["id"] if eligible else None
    return {"quotes": qs, "available": avail, "lowest": lowest,
            "rows": [{"q": q, "diff": avail - q["total"], "over": q["total"] > avail} for q in qs]}


def select_quote(db, pid, rid, qid, reason, actor_id):
    r = _open(db, pid, rid)
    if r["status"] not in OPEN:
        raise AuthError(_("A quote is chosen while the request is collecting quotes."))
    if r["created_by"] == actor_id:
        raise AuthError(_("Whoever raises the request can't choose the quote."))
    cmp = comparison(db, r)
    if len(cmp["quotes"]) < MIN_QUOTES:
        raise AuthError(_("At least {n} quotes are needed before choosing.", n=MIN_QUOTES))
    q = next((x for x in cmp["quotes"] if x["id"] == qid), None)
    if q is None or q["evaluation"] == "non_compliant":
        raise AuthError(_("Choose a technically compliant quote."))
    reason = (reason or "").strip() or None
    if qid != cmp["lowest"] and (not reason or len(reason) < 5):
        raise AuthError(_("This is not the lowest quote. Write the reason for choosing it."))
    with tx(db):
        db.execute("UPDATE purchase_requests SET status = 'selected', selected_quote_id = ?, selection_reason = ?, "
                   "selected_at = ?, selected_by = ?, return_reason = NULL WHERE id = ?", (qid, reason, utcnow(), actor_id, rid))
        audit.log(db, actor_id, "pr_selected", "project", pid, pid, code=r["code"], amount=q["total"], reason=reason)


def _needs_director(db, r, q) -> bool:
    """فوق 10,000 ريال، أو إذا تجاوز مجموع أوامر نفس البند ونفس الجهة خلال 30 يومًا الحد (منع التجزئة)."""
    if q["total"] > LIMIT:
        return True
    since = (date.today() - timedelta(days=SPLIT_DAYS)).isoformat()
    recent = db.execute("SELECT CAST(COALESCE(SUM(total), 0) AS BIGINT) FROM commitments WHERE boq_item_id = ? AND entity_id = ? "
                        "AND issued_at >= ?", (r["boq_item_id"], q["entity_id"], since)).fetchone()[0]
    return recent + q["total"] > LIMIT


def cc_approve(db, pid, rid, actor_id) -> str | None:
    """اعتماد مهندس تحكم تكلفة. حتى الحد يصدر الأمر فورًا، وفوقه ينتظر المدير التنفيذي."""
    r = _open(db, pid, rid)
    if r["status"] != "selected":
        raise AuthError(_("This request is not waiting for cost control."))
    if actor_id in (r["created_by"], r["selected_by"]):
        raise AuthError(_("Whoever raises or chooses can't approve."))
    q = db.execute("SELECT * FROM quotes WHERE id = ?", (r["selected_quote_id"],)).fetchone()
    if q["total"] > available(db, r["boq_item_id"]):
        raise AuthError(_("The chosen quote exceeds the available budget of the item ({avail} SAR). A change request is needed "
                          "first.", avail=fmt_money(available(db, r["boq_item_id"]))))
    needs = _needs_director(db, r, q)
    with tx(db):
        db.execute("UPDATE purchase_requests SET cc_at = ?, cc_by = ?, needs_director = ?, status = ? WHERE id = ?",
                   (utcnow(), actor_id, needs, "cc_approved" if needs else "approved", rid))
        audit.log(db, actor_id, "pr_cc_approved", "project", pid, pid, code=r["code"], amount=q["total"])
        return None if needs else _issue(db, pid, r, q, actor_id)


def director_approve(db, pid, rid, actor_id) -> str:
    r = _open(db, pid, rid)
    if r["status"] != "cc_approved":
        raise AuthError(_("This request is not waiting for the Director."))
    if actor_id in (r["created_by"], r["selected_by"], r["cc_by"]):
        raise AuthError(_("Whoever raises or chooses can't approve."))
    q = db.execute("SELECT * FROM quotes WHERE id = ?", (r["selected_quote_id"],)).fetchone()
    if q["total"] > available(db, r["boq_item_id"]):
        raise AuthError(_("The chosen quote exceeds the available budget of the item ({avail} SAR). A change request is needed "
                          "first.", avail=fmt_money(available(db, r["boq_item_id"]))))
    with tx(db):
        db.execute("UPDATE purchase_requests SET dir_at = ?, dir_by = ?, status = 'approved' WHERE id = ?", (utcnow(), actor_id, rid))
        audit.log(db, actor_id, "pr_director_approved", "project", pid, pid, code=r["code"], amount=q["total"])
        return _issue(db, pid, r, q, actor_id)


def _issue(db, pid, r, q, actor_id) -> str:
    """تُصدر المنصة أمر الشراء أو عقد مقاول الباطن، ويُسجَّل التزامًا على ميزانية البند."""
    p = db.execute("SELECT code FROM projects WHERE id = ?", (pid,)).fetchone()
    if r["kind"] == "subcontract":
        code = f"{p['code']}-SC-{next_counter(db, 'sc-%d' % pid):03d}"
    else:
        code = f"{p['code']}-PO-{next_counter(db, 'po-%d' % pid):04d}"
    db.execute("INSERT INTO commitments(project_id, request_id, quote_id, code, kind, entity_id, boq_item_id, qty_milli, unit_price, "
               "total, issued_at, issued_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
               (pid, r["id"], q["id"], code, r["kind"], q["entity_id"], r["boq_item_id"], r["qty_milli"], q["unit_price"],
                q["total"], utcnow(), actor_id))
    audit.log(db, actor_id, "order_issued", "project", pid, pid, code=code, amount=q["total"])
    return code


def return_request(db, pid, rid, reason, actor_id, may_director=False):
    """إرجاع مع ذكر السبب: من مهندس تحكم تكلفة قبل اعتماده، أو من المدير التنفيذي قبل اعتماده."""
    r = _open(db, pid, rid)
    if r["status"] == "cc_approved" and not may_director:
        raise AuthError(_("This request is not waiting for cost control."))
    if r["status"] not in ("selected", "cc_approved"):
        raise AuthError(_("Only a request waiting for approval can be returned."))
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise AuthError(_("Write the reason for returning."))
    with tx(db):
        db.execute("UPDATE purchase_requests SET status = 'returned', return_reason = ?, selected_quote_id = NULL, "
                   "selection_reason = NULL, selected_at = NULL, selected_by = NULL, cc_at = NULL, cc_by = NULL WHERE id = ?",
                   (reason, rid))
        audit.log(db, actor_id, "pr_returned", "project", pid, pid, code=r["code"], reason=reason)


def cancel_request(db, pid, rid, reason, actor_id):
    r = _open(db, pid, rid)
    if r["status"] in ("approved", "cancelled"):
        raise AuthError(_("This request can't be cancelled."))
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise AuthError(_("Write the reason for cancelling."))
    with tx(db):
        db.execute("UPDATE purchase_requests SET status = 'cancelled', return_reason = ? WHERE id = ?", (reason, rid))
        audit.log(db, actor_id, "pr_cancelled", "project", pid, pid, code=r["code"], reason=reason)


def budget_by_item(db, pid):
    """لكل بند: الميزانية، والملتزم به، والمتاح."""
    rows = db.execute("SELECT id, code, description, amount FROM boq_items WHERE project_id = ? ORDER BY code", (pid,)).fetchall()
    out = []
    for b in rows:
        c = committed(db, b["id"])
        if c:
            out.append({"item": b, "committed": c, "available": b["amount"] - c})
    return out

