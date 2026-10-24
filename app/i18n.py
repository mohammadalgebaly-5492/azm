"""الواجهة بلغتين: العربية (افتراضية) والإنجليزية.

كل نص يظهر للمستخدم يُكتب بالإنجليزية داخل _("...")، وترجمته العربية في i18n_ar.py.
اختبار tests/test_i18n.py يفشل لو أي نص بدون ترجمة عربية.
"""
from flask import g, has_request_context, redirect, request

from .i18n_ar import AR

LANGS = {"ar": "rtl", "en": "ltr"}
DEFAULT_LANG = "ar"
COOKIE = "lang"


def current_lang() -> str:
    if has_request_context():
        return g.get("lang") or DEFAULT_LANG
    return DEFAULT_LANG


def _(text: str, **values) -> str:
    if current_lang() == "ar":
        text = AR.get(text, text)
    return text.format(**values) if values else text


def init_lang():
    lang = request.cookies.get(COOKIE)
    g.lang = lang if lang in LANGS else DEFAULT_LANG


def switch(lang: str, next_url: str):
    resp = redirect(next_url)
    if lang in LANGS:
        resp.set_cookie(COOKIE, lang, max_age=365 * 24 * 3600, samesite="Lax", path="/")
    return resp
