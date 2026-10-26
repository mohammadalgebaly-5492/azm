"""المخزن الرئيسي للشركة والسقالات (طلب م. محمد 2026-10-26): مكونات السقالات من دليل المواد (نوع SCF)، وكمياتها في المخزن
الرئيسي وفي موقع كل مشروع والمركّب منها. أمين المخزن (stores.manage) يسجّل الوارد والصرف للموقع والإرجاع، ومهندس الموقع
(schedule.manage) يسجّل التركيب والفك. لكل قطعة إيجار يومي من يوم صرفها للمشروع حتى إرجاعها، ملكًا للشركة كانت أو مستأجرة،
ويدخل في التكلفة الفعلية لبند جدول الكميات الذي صُرفت له. والتالف أو المفقود يُسجّل بسبب ويُخصم."""
from datetime import date, timedelta

from . import audit
from .db import next_counter, tx, utcnow
from .errors import AuthError
from .i18n import _
from .projects import parse_money
from .resources import _date

KINDS = {"receive": "Received into the store", "issue": "Issued to the site", "install": "Installation",
         "dismantle": "Dismantling", "return": "Returned to the store", "loss": "Damaged or lost"}
PLACES = {"store": "In the store", "site": "On site, not installed", "use": "Installed"}
STORE_KINDS = ("receive", "issue", "return")      # أمين المخزن
SITE_KINDS = ("install", "dismantle")             # مهندس الموقع


def components(db):
    return db.execute("SELECT c.code, c.name_ar, c.name_en, c.unit_code, s.daily_rate FROM stock_items s "
                      "JOIN catalog_items c ON c.kind = 'material' AND c.code = s.material_code ORDER BY c.sort, c.code").fetchall()


def _moves(db, pid=None):
    sql = "SELECT * FROM stock_moves" + (" WHERE project_id = ?" if pid else "") + " ORDER BY on_date, id"
    return db.execute(sql, (pid,) if pid else ()).fetchall()


def _sign(m):
    """أثر الحركة على (المخزن، الموجود مع المشروع، المركّب)."""
    k, q, place = m["kind"], m["qty"], m["place"]
    return {"receive": (q, 0, 0), "issue": (-q, q, 0), "return": (q, -q, 0), "install": (0, 0, q), "dismantle": (0, 0, -q),
            "loss": (-q, 0, 0) if place == "store" else (0, -q, -q if place == "use" else 0)}[k]


def store_balance(db) -> dict:
    """لكل مكوّن: في المخزن، ومع المشاريع، ومركّب."""
    out = {c["code"]: {"store": 0, "out": 0, "use": 0} for c in components(db)}
    for m in _moves(db):
        s, o, u = _sign(m)
        b = out.setdefault(m["material_code"], {"store": 0, "out": 0, "use": 0})
        b["store"] += s
        b["out"] += o
        b["use"] += u
    return out


def project_balance(db, pid) -> dict:
    """لكل (بند، مكوّن) في المشروع: الموجود مع المشروع، والمركّب، والموجود في الموقع غير مركّب."""
    out = {}
    for m in _moves(db, pid):
        _s, o, u = _sign(m)
        b = out.setdefault((m["boq_item_id"], m["material_code"]), {"out": 0, "use": 0})
        b["out"] += o
        b["use"] += u
    for b in out.values():
        b["site"] = b["out"] - b["use"]
    return out


def _qty(raw):
    try:
        q = int(str(raw or "").replace(",", "").strip())
    except ValueError:
        q = 0
    if q <= 0:
        raise AuthError(_("Enter the number of pieces."))
    return q


def record(db, form, actor_id, pid=None) -> str:
    kind = form.get("kind") or ""
    if kind not in KINDS:
        raise AuthError(_("Choose the movement."))
    code = form.get("material_code") or ""
    if not db.execute("SELECT 1 FROM stock_items WHERE material_code = ?", (code,)).fetchone():
        raise AuthError(_("Choose the scaffolding component."))
    qty = _qty(form.get("qty"))
    on = _date(form.get("on_date"), _("the movement date"))
    if on > date.today().isoformat():
        raise AuthError(_("Actual dates can't be in the future."))
    place = form.get("place") if kind == "loss" else None
    if kind == "loss" and place not in PLACES:
        raise AuthError(_("Choose where the pieces were damaged or lost."))
    reason = (form.get("reason") or "").strip() or None
    if kind == "loss" and (not reason or len(reason) < 5):
        raise AuthError(_("Write the reason for the damage or loss."))
    on_project = kind not in ("receive",) and not (kind == "loss" and place == "store")
    item = None
    if on_project:
        raw = str(form.get("boq_item_id") or "")
        item = db.execute("SELECT id FROM boq_items WHERE id = ? AND project_id = ?", (int(raw), pid)).fetchone() \
            if pid and raw.isdigit() else None
        if item is None:
            raise AuthError(_("Choose the BOQ item the scaffolding serves."))
    store = store_balance(db).get(code, {"store": 0})["store"]
    here = project_balance(db, pid).get((item["id"], code), {"out": 0, "use": 0, "site": 0}) if item else None
    need = {"issue": store, "return": here and here["site"], "install": here and here["site"],
            "dismantle": here and here["use"]}.get(kind)
    if kind == "loss":
        need = store if place == "store" else here["site"] if place == "site" else here["use"]
    if need is not None and qty > need:
        raise AuthError(_("Only {n} pieces are available for this movement.", n=need))
    with tx(db):
        mcode = f"STM-{next_counter(db, 'stock-moves'):05d}"
        db.execute("INSERT INTO stock_moves(code, kind, material_code, qty, project_id, boq_item_id, place, on_date, reason, "
                   "created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (mcode, kind, code, qty, pid if on_project else None, item["id"] if item else None, place, on, reason,
                    utcnow(), actor_id))
        audit.log(db, actor_id, "stock_moved", "project" if on_project else "catalog", pid if on_project else None,
                  pid if on_project else None, code=mcode, count=qty, **({"reason": reason} if reason else {}))
    return mcode


def set_rate(db, code, raw, actor_id):
    value = parse_money(raw)
    if value is None or value < 0:
        raise AuthError(_("Enter the daily rent of one piece in SAR."))
    if not db.execute("SELECT 1 FROM stock_items WHERE material_code = ?", (code,)).fetchone():
        raise AuthError(_("Choose the scaffolding component."))
    with tx(db):
        db.execute("UPDATE stock_items SET daily_rate = ? WHERE material_code = ?", (value, code))
        audit.log(db, actor_id, "stock_rate_set", "catalog", None, code=code, amount=value)


def moves(db, pid=None, limit=50):
    sql = ("SELECT m.*, u.full_name, b.code AS item_code, p.code AS project_code FROM stock_moves m "
           "JOIN users u ON u.id = m.created_by LEFT JOIN boq_items b ON b.id = m.boq_item_id "
           "LEFT JOIN projects p ON p.id = m.project_id" + (" WHERE m.project_id = ?" if pid else "")
           + " ORDER BY m.on_date DESC, m.id DESC LIMIT ?")
    return db.execute(sql, ((pid, limit) if pid else (limit,))).fetchall()


def cost_by_item(db, pid, until=None) -> dict[int, int]:
    """إيجار السقالات لكل بند: عدد القطع الموجودة مع المشروع في كل يوم × الإيجار اليومي، من يوم الصرف حتى يوم الإرجاع
    (يوم الإرجاع لا يُحسب)، وحتى تاريخ إن طُلب."""
    rates = {c["code"]: c["daily_rate"] for c in components(db)}
    end = date.fromisoformat(str(until)[:10]) if until else date.today()
    stop = end + timedelta(days=1)
    held, since, cost = {}, {}, {}
    for m in _moves(db, pid):
        on = date.fromisoformat(str(m["on_date"])[:10])
        if on > end:
            break
        key = (m["boq_item_id"], m["material_code"])
        _s, o, _u = _sign(m)
        if not o:
            continue
        if key in since:
            cost[key[0]] = cost.get(key[0], 0) + held[key] * (on - since[key]).days * rates.get(key[1], 0)
        held[key] = held.get(key, 0) + o
        since[key] = on
    for key, n in held.items():
        cost[key[0]] = cost.get(key[0], 0) + n * (stop - since[key]).days * rates.get(key[1], 0)
    return {k: v for k, v in cost.items() if k and v}


def daily_rent(db, pid) -> int:
    rates = {c["code"]: c["daily_rate"] for c in components(db)}
    return sum(b["out"] * rates.get(code, 0) for (_i, code), b in project_balance(db, pid).items())
