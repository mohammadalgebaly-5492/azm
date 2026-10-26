"""تقارير المهندس (قرار م. محمد 2026-10-26): نص و/أو ملف PDF على كل ما يرفعه المهندس: التقرير اليومي، وطلب الشراء، وطلب
التغيير، والمستخلص والفاتورة، ومحضر الاستلام. تُضاف ولا تُحذف، ويراها كل من يرى المشروع، ويضيفها من يملك صلاحية رفع المستند."""
from . import audit, files
from .db import tx, utcnow
from .errors import AuthError
from .i18n import _

# النوع: (الجدول، صلاحية الإضافة، اسم المستند)
DOCS = {"dsr": ("daily_reports", "schedule.manage", "Daily site report"),
        "pr": ("purchase_requests", "procurement.request", "Purchase request"),
        "cr": ("change_requests", "changes.request", "Change request"),
        "payable": ("payables", "payables.raise", "Certificate or invoice"),
        "grn": ("goods_receipts", "payables.raise", "Goods receipt")}
MAX_TEXT = 5000


def doc(db, pid, kind, doc_id):
    if kind not in DOCS:
        raise AuthError(_("This document doesn't exist."))
    d = db.execute(f"SELECT * FROM {DOCS[kind][0]} WHERE id = ? AND project_id = ?", (doc_id, pid)).fetchone()
    if d is None:
        raise AuthError(_("This document doesn't exist."))
    return d


def entries(db, pid, kind, doc_id):
    return db.execute("SELECT a.*, u.full_name FROM attachments a JOIN users u ON u.id = a.created_by "
                      "WHERE a.project_id = ? AND a.doc_kind = ? AND a.doc_id = ? ORDER BY a.id", (pid, kind, doc_id)).fetchall()


def counts(db, pid, kind) -> dict[int, int]:
    return {r[0]: r[1] for r in db.execute("SELECT doc_id, COUNT(*) FROM attachments WHERE project_id = ? AND doc_kind = ? "
                                           "GROUP BY doc_id", (pid, kind)).fetchall()}


def add(db, pid, kind, doc_id, text, stream, filename, actor_id) -> str:
    d = doc(db, pid, kind, doc_id)
    text = (text or "").strip()
    if len(text) > MAX_TEXT:
        raise AuthError(_("The report text is longer than {n} characters.", n=MAX_TEXT))
    data = files.read_pdf(stream) if filename else None
    if not text and data is None:
        raise AuthError(_("Write the report or choose a PDF file."))
    key = None
    if data is not None:
        project = db.execute("SELECT code FROM projects WHERE id = ?", (pid,)).fetchone()["code"]
        n = db.execute("SELECT COUNT(*) FROM attachments WHERE doc_kind = ? AND doc_id = ? AND storage_key IS NOT NULL",
                       (kind, doc_id)).fetchone()[0] + 1
        key = f"{project}/reports/{d['code']}-R{n:02d}.pdf"
        files.put(key, data)
    with tx(db):
        db.execute("INSERT INTO attachments(project_id, doc_kind, doc_id, body, file_name, size_bytes, storage_key, created_at, "
                   "created_by) VALUES (?,?,?,?,?,?,?,?,?)",
                   (pid, kind, doc_id, text or None, filename[:120] if data is not None else None,
                    len(data) if data is not None else None, key, utcnow(), actor_id))
        audit.log(db, actor_id, "report_attached", "project", pid, pid, code=d["code"])
    return d["code"]


def content(db, pid, aid) -> tuple[bytes, str]:
    a = db.execute("SELECT * FROM attachments WHERE id = ? AND project_id = ?", (aid, pid)).fetchone()
    if a is None or not a["storage_key"]:
        raise AuthError(_("The file is not found."))
    return files.get(a["storage_key"]), a["storage_key"].rsplit("/", 1)[-1]
