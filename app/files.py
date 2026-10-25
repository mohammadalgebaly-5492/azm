"""حفظ الملفات: حاوية خاصة في Supabase Storage على المنصة، أو مجلد محلي للتجربة والاختبارات.

على المنصة يضبط المبرمج: SUPABASE_URL وSUPABASE_SERVICE_ROLE_KEY (واختياريًا SUPABASE_STORAGE_BUCKET، الافتراضي azm-files).
بدونها لا يعمل الرفع على Vercel (ملفاته للقراءة فقط)، وتعرض الشاشات أن الرفع ينتظر مكان حفظ الملفات."""
import os
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app

from .errors import AuthError
from .i18n import _

MAX_BYTES = 4 * 1024 * 1024  # حد Vercel لحجم الطلب 4.5 MB


def _supabase():
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    return (url.rstrip("/"), key, os.environ.get("SUPABASE_STORAGE_BUCKET", "azm-files")) if url and key else None


def _local_dir():
    if os.environ.get("VERCEL"):
        return None
    return current_app.config.get("UPLOAD_DIR") or os.path.join(current_app.instance_path, "uploads")


def enabled() -> bool:
    return bool(_supabase() or _local_dir())


def _request(method, key, data=None, content_type=None):
    url, secret, bucket = _supabase()
    req = urllib.request.Request(f"{url}/storage/v1/object/{bucket}/{urllib.parse.quote(key)}", data=data, method=method,
                                 headers={"Authorization": f"Bearer {secret}", "apikey": secret,
                                          **({"Content-Type": content_type} if content_type else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    except (urllib.error.URLError, TimeoutError) as e:
        current_app.logger.error("storage %s %s failed: %s", method, key, e)
        raise AuthError(_("File storage is not reachable now. Try again later."))


def read_pdf(stream) -> bytes:
    data = stream.read(MAX_BYTES + 1) if stream else b""
    if not data:
        raise AuthError(_("Choose the PDF file."))
    if len(data) > MAX_BYTES:
        raise AuthError(_("The file is larger than 4 MB."))
    if not data.startswith(b"%PDF-"):
        raise AuthError(_("The file must be a PDF."))
    return data


def put(key, data: bytes, content_type="application/pdf"):
    if _supabase():
        return _request("POST", key, data, content_type)
    base = _local_dir()
    if base is None:
        raise AuthError(_("Uploading waits for file storage, which the programmer will add."))
    path = os.path.join(base, *key.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "xb") as f:  # لا يُستبدل ملف محفوظ
        f.write(data)


def get(key) -> bytes:
    if _supabase():
        return _request("GET", key)
    base = _local_dir()
    path = os.path.join(base, *key.split("/")) if base else None
    if path is None or not os.path.isfile(path):
        raise AuthError(_("The file is not found."))
    with open(path, "rb") as f:
        return f.read()
