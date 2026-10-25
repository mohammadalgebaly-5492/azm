// AZM — سلوك الواجهة. بلا مكتبات خارجية.
//
// البنية:
//   1) تنقّل داخل الصفحة: الروابط تجلب الصفحة التالية وتستبدل المحتوى فقط بانتقال ناعم (بدون إعادة تحميل).
//   2) "محسّنات" تُطبَّق على المحتوى عند التحميل وبعد كل تنقّل: القوائم المنسدلة، التقويم، الدليل، العدّادات...
//   3) سلوك عام عبر تفويض الأحداث: القائمة الجانبية، النسخ، المظهر، التلميحات...
// أي ميزة جديدة تحتاج تهيئة عناصر: أضف دالة إلى ENHANCERS.

const ENHANCERS = [];
const enhance = (root) => { if (root) ENHANCERS.forEach((fn) => fn(root)); };
const RTL = () => document.documentElement.dir === "rtl";
const reduceMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* التخزين غير متاح */ } },
};

// ---------- طبقة عائمة: القوائم والتقويم تُعرض فوق الصفحة فلا يقصّها أي إطار ----------
const Float = (() => {
  let current = null;
  const place = () => {
    if (!current) return;
    const { anchor, el } = current;
    const r = anchor.getBoundingClientRect();
    el.style.minWidth = `${Math.max(r.width, 220)}px`;
    const w = el.offsetWidth, h = el.offsetHeight;
    let x = RTL() ? r.right - w : r.left;
    x = Math.max(8, Math.min(x, innerWidth - w - 8));
    const below = r.bottom + 6 + h <= innerHeight - 8 || r.top - 6 - h < 8;
    el.style.left = `${x}px`;
    el.style.top = `${below ? r.bottom + 6 : r.top - 6 - h}px`;
  };
  const close = (focus) => {
    if (!current) return;
    const c = current; current = null;
    c.el.remove();
    c.anchor.setAttribute("aria-expanded", "false");
    if (focus) c.anchor.focus();
  };
  addEventListener("resize", place);
  addEventListener("scroll", place, { passive: true, capture: true });
  document.addEventListener("pointerdown", (e) => {
    if (current && !current.el.contains(e.target) && !current.anchor.contains(e.target)) close();
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && current) { e.preventDefault(); close(true); } });
  document.addEventListener("azm:navigated", () => close());
  return {
    open(anchor, el) {
      close();
      el.classList.add("float");
      document.body.append(el);
      current = { anchor, el };
      anchor.setAttribute("aria-expanded", "true");
      place();
      return el;
    },
    close,
    isOpenFor: (anchor) => !!current && current.anchor === anchor,
    place,
  };
})();

// ---------- 1) التنقّل داخل الصفحة ----------
(() => {
  const skip = (a, url) =>
    a.target || a.hasAttribute("download") || "noNav" in a.dataset || url.origin !== location.origin ||
    url.pathname.startsWith("/static/") || /\.(xlsx|csv|pdf|png|jpe?g)$/i.test(url.pathname) ||
    url.pathname.startsWith("/lang/") || url.pathname.startsWith("/avatar/") ||
    (url.pathname === location.pathname && url.search === location.search && url.hash);
  let busy = null;

  async function go(href, { push = true, scroll = true } = {}) {
    if (busy) busy.abort();
    const ctrl = new AbortController();
    busy = ctrl;
    const root = document.documentElement;
    const slow = setTimeout(() => root.classList.add("loading"), 120);
    let res, html;
    try {
      res = await fetch(href, { signal: ctrl.signal, headers: { "X-AZM-Nav": "1" }, credentials: "same-origin" });
      if (!(res.headers.get("content-type") || "").includes("text/html")) { location.href = href; return; }
      html = await res.text();
    } catch (e) {
      if (e.name !== "AbortError") location.href = href;
      return;
    } finally {
      clearTimeout(slow);
      if (busy === ctrl) { busy = null; root.classList.remove("loading"); }
    }
    const doc = new DOMParser().parseFromString(html, "text/html");
    const next = doc.querySelector(".main"), here = document.querySelector(".main");
    // صفحات خارج التطبيق (الدخول، الأخطاء العامة) أو تغيّر اللغة: تحميل كامل
    if (!next || !here || doc.documentElement.lang !== root.lang) { location.href = res.url; return; }
    const swap = () => {
      here.replaceWith(next);
      document.title = doc.title;
      const nav = doc.querySelector(".sidebar .nav"), myNav = document.querySelector(".sidebar .nav");
      if (nav && myNav) myNav.replaceWith(nav);
      const tb = doc.querySelector(".topbar-title"), myTb = document.querySelector(".topbar-title");
      if (tb && myTb) myTb.textContent = tb.textContent;
      document.body.classList.remove("nav-open");
      enhance(next);
      enhance(document.querySelector(".sidebar .nav"));
    };
    if (push) history.pushState({ azm: 1 }, "", res.redirected ? res.url : href);
    if (document.startViewTransition && !reduceMotion()) await document.startViewTransition(swap).updateCallbackDone;
    else swap();
    const target = location.hash && document.getElementById(location.hash.slice(1));
    if (target) target.scrollIntoView();
    else if (scroll) scrollTo({ top: 0 });
    document.dispatchEvent(new Event("azm:navigated"));
  }

  document.addEventListener("click", (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest("a[href]");
    if (!a || !document.querySelector(".main")) return;
    const url = new URL(a.href, location.href);
    if (skip(a, url)) return;
    e.preventDefault();
    go(url.href);
  });
  if (document.querySelector(".main")) history.replaceState({ azm: 1 }, "");
  addEventListener("popstate", (e) => { if (e.state && e.state.azm) go(location.href, { push: false, scroll: false }); });
})();

// ---------- 3) سلوك عام ----------
// قائمة الجوال
document.addEventListener("click", (e) => {
  if (e.target.closest("[data-nav-toggle]")) document.body.classList.toggle("nav-open");
  else if (e.target.closest("[data-nav-close]")) document.body.classList.remove("nav-open");
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") document.body.classList.remove("nav-open"); });

// الشريط العلوي للجوال: زجاجي بعد التمرير، ويعرض عنوان الصفحة بعد تجاوز العنوان الكبير
(() => {
  let ticking = false;
  const update = () => {
    ticking = false;
    const h1 = document.querySelector(".main h1");
    document.body.classList.toggle("scrolled", scrollY > 4);
    document.body.classList.toggle("titled", !!h1 && h1.getBoundingClientRect().bottom < 56);
  };
  addEventListener("scroll", () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
  document.addEventListener("azm:navigated", update);
  update();
})();

// زر النسخ: data-copy="#id" ونص التأكيد في data-done
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-copy]");
  if (!b) return;
  const el = document.querySelector(b.dataset.copy);
  const label = b.querySelector("span");
  if (!el || !label) return;
  const done = () => { const t = label.textContent; label.textContent = b.dataset.done || "✓"; setTimeout(() => (label.textContent = t), 1800); };
  const fallback = () => { const r = document.createRange(); r.selectNodeContents(el); const s = getSelection(); s.removeAllRanges(); s.addRange(r); };
  if (navigator.clipboard) navigator.clipboard.writeText(el.textContent.trim()).then(done, fallback); else fallback();
});

// قائمة إجراءات واحدة مفتوحة في نفس الوقت، وتُغلق عند الضغط خارجها
document.addEventListener("click", (e) => {
  document.querySelectorAll("details.menu[open]").forEach((d) => { if (!d.contains(e.target)) d.removeAttribute("open"); });
});

// مفاتيح تُحفظ فور التغيير: data-autosubmit
document.addEventListener("change", (e) => { if (e.target.matches("[data-autosubmit]")) e.target.form.requestSubmit(); });

// بقعة ضوء تتبع المؤشر فوق البطاقات
document.addEventListener("pointermove", (e) => {
  const card = e.target.closest(".spot");
  if (!card) return;
  const r = card.getBoundingClientRect();
  card.style.setProperty("--x", `${e.clientX - r.left}px`);
  card.style.setProperty("--y", `${e.clientY - r.top}px`);
}, { passive: true });

// تلميحات الرسوم البيانية: أي عنصر فيه data-tip يعرض قيمته عند المرور أو التركيز
(() => {
  const tip = document.createElement("div");
  tip.className = "guide-tip";
  tip.setAttribute("role", "tooltip");
  document.body.append(tip);
  const show = (el) => {
    tip.textContent = el.dataset.tip;
    tip.classList.add("show");
    const r = el.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = `${Math.max(12, Math.min(r.left + r.width / 2 - w / 2, innerWidth - w - 12))}px`;
    tip.style.top = `${r.top - h - 8 < 8 ? r.bottom + 8 : r.top - h - 8}px`;
  };
  const hide = () => tip.classList.remove("show");
  document.addEventListener("mouseover", (e) => { const el = e.target.closest("[data-tip]"); if (el) show(el); });
  document.addEventListener("mouseout", (e) => { if (e.target.closest("[data-tip]")) hide(); });
  document.addEventListener("focusin", (e) => { const el = e.target.closest("[data-tip]"); if (el) show(el); });
  document.addEventListener("focusout", hide);
  addEventListener("scroll", hide, { passive: true });
  document.addEventListener("azm:navigated", hide);
})();

// ---------- 2) المحسّنات ----------
// المجموعات الشجرية في القائمة الجانبية: تتذكر الفتح والإغلاق
ENHANCERS.push((root) => {
  root.querySelectorAll("details.nav-tree").forEach((d) => {
    const key = `azm-tree-${d.dataset.tree}`, saved = store.get(key);
    if (saved === "1") d.open = true;
    else if (saved === "0" && !d.querySelector(".nav-sub.on")) d.open = false;
    d.addEventListener("toggle", () => store.set(key, d.open ? "1" : "0"));
  });
});

// البطاقات: بقعة الضوء
ENHANCERS.push((root) => { root.querySelectorAll(".card, .stat").forEach((c) => c.classList.add("spot")); });

// الأرقام تعدّ تصاعديًا عند الظهور: data-count
ENHANCERS.push((root) => {
  root.querySelectorAll("[data-count]").forEach((el) => {
    const end = Number(el.dataset.count);
    if (!isFinite(end) || reduceMotion() || end === 0) return;
    const start = performance.now(), dur = 700;
    const step = (t) => {
      const k = Math.min(1, (t - start) / dur), v = end * (1 - Math.pow(1 - k, 3));
      el.textContent = Math.round(v).toLocaleString("en-US");
      if (k < 1) requestAnimationFrame(step);
    };
    el.textContent = "0";
    requestAnimationFrame(step);
  });
});

// حساب الإجمالي أثناء الكتابة في نموذج البند (للعرض فقط؛ الحساب المعتمد على الخادم)
const toNumber = (v) => parseFloat(String(v).replace(/[,٬\s]/g, "").replace(/[٠-٩]/g, (d) => "٠١٢٣٤٥٦٧٨٩".indexOf(d)).replace("٫", "."));
ENHANCERS.push((root) => {
  root.querySelectorAll("output[data-calc]").forEach((out) => {
    const [a, b] = out.dataset.calc.split(",").map((id) => document.getElementById(id));
    if (!a || !b) return;
    const upd = () => {
      const q = toNumber(a.value), r = toNumber(b.value);
      out.textContent = isFinite(q) && isFinite(r) ? (Math.round(q * r * 100) / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—";
    };
    a.addEventListener("input", upd); b.addEventListener("input", upd);
  });
});

// حقول المبالغ: فواصل الآلاف عند الخروج من الحقل (الخادم يقبل الصيغتين)
ENHANCERS.push((root) => {
  root.querySelectorAll("input[data-money]").forEach((el) => el.addEventListener("blur", () => {
    const n = toNumber(el.value);
    if (isFinite(n)) el.value = n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }));
});

// منتقي التاريخ: يستبدل <input type="date"> بزر وتقويم عائم يتبع لغة الصفحة واتجاهها.
// القيمة المرسلة تبقى بصيغة ISO (YYYY-MM-DD) في الحقل الأصلي بعد إخفائه.
const svg = (d, s = 16) => `<svg class="ic" width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
const ISO = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parseISO = (v) => { const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v || ""); return m ? new Date(+m[1], m[2] - 1, +m[3]) : null; };
ENHANCERS.push((root) => {
  const lang = document.documentElement.lang === "ar" ? "ar-u-ca-gregory-nu-latn" : "en-GB";
  const fmtLong = new Intl.DateTimeFormat(lang, { day: "numeric", month: "long", year: "numeric" });
  const fmtMonth = new Intl.DateTimeFormat(lang, { month: "long", year: "numeric" });
  const fmtWd = new Intl.DateTimeFormat(lang, { weekday: "narrow" });
  const CAL = svg('<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>');
  const PREV = svg('<path d="M15 5l-7 7 7 7"/>'), NEXT = svg('<path d="M9 5l7 7-7 7"/>');

  root.querySelectorAll('input[type="date"]').forEach((input) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "dp-field";
    btn.setAttribute("aria-haspopup", "dialog");
    btn.setAttribute("aria-expanded", "false");
    if (input.id) { const lbl = document.querySelector(`label[for="${input.id}"]`); if (lbl) { btn.id = `${input.id}_btn`; lbl.htmlFor = btn.id; } }
    input.before(btn);
    input.type = "hidden";
    const show = () => { const d = parseISO(input.value); btn.innerHTML = `<span class="${d ? "" : "ph"}">${d ? fmtLong.format(d) : (input.dataset.placeholder || "—")}</span>${CAL}`; };
    show();
    input.addEventListener("change", show);

    btn.addEventListener("click", () => {
      if (Float.isOpenFor(btn)) return Float.close(true);
      const pop = document.createElement("div");
      pop.className = "dp-pop";
      pop.setAttribute("role", "dialog");
      let view = parseISO(input.value) || parseISO(input.min) || new Date();
      const render = () => {
        const sel = parseISO(input.value), today = new Date(), min = parseISO(input.min), max = parseISO(input.max);
        const first = new Date(view.getFullYear(), view.getMonth(), 1);
        const start = new Date(first); start.setDate(1 - first.getDay());
        let html = `<div class="dp-head"><button type="button" class="btn btn-ghost btn-icon btn-sm" data-m="-1" aria-label="‹">${PREV}</button>
          <b>${fmtMonth.format(view)}</b><button type="button" class="btn btn-ghost btn-icon btn-sm" data-m="1" aria-label="›">${NEXT}</button></div><div class="dp-grid">`;
        for (let i = 0; i < 7; i++) html += `<span class="wd">${fmtWd.format(new Date(2026, 1, 1 + i))}</span>`;
        for (let i = 0; i < 42; i++) {
          const d = new Date(start); d.setDate(start.getDate() + i);
          const cls = ["dp-day", d.getMonth() !== view.getMonth() && "out", ISO(d) === ISO(today) && "today", sel && ISO(d) === ISO(sel) && "sel"].filter(Boolean).join(" ");
          const off = (min && d < min) || (max && d > max);
          html += `<button type="button" class="${cls}" data-d="${ISO(d)}"${off ? " disabled" : ""}>${d.getDate()}</button>`;
        }
        html += `</div><div class="dp-foot"><button type="button" class="btn btn-ghost btn-sm" data-today>${input.dataset.today || "Today"}</button>
          <button type="button" class="btn btn-ghost btn-sm" data-clear>${input.dataset.clear || "Clear"}</button></div>`;
        pop.innerHTML = html;
        Float.place();
      };
      const pick = (v) => { input.value = v; input.dispatchEvent(new Event("change", { bubbles: true })); Float.close(true); };
      pop.addEventListener("click", (e) => {
        const t = e.target.closest("button");
        if (!t) return;
        if (t.dataset.m) { view = new Date(view.getFullYear(), view.getMonth() + Number(t.dataset.m), 1); render(); }
        else if (t.dataset.d) pick(t.dataset.d);
        else if ("today" in t.dataset) pick(ISO(new Date()));
        else if ("clear" in t.dataset) pick("");
      });
      render();
      Float.open(btn, pop);
      (pop.querySelector(".dp-day.sel") || pop.querySelector(".dp-day.today") || pop.querySelector(".dp-day")).focus({ preventScroll: true });
    });
  });

  // تاريخ النهاية لا يسبق تاريخ البداية: data-after="start_date"
  root.querySelectorAll("input[data-after]").forEach((end) => {
    const startInput = document.getElementById(end.dataset.after);
    if (!startInput) return;
    const sync = () => { end.min = startInput.value || ""; };
    startInput.addEventListener("change", sync); sync();
  });

  // قراءة المدة بين تاريخين: <output data-duration="start,end" data-days="{n} days">
  root.querySelectorAll("output[data-duration]").forEach((out) => {
    const [a, b] = out.dataset.duration.split(",").map((id) => document.getElementById(id));
    if (!a || !b) return;
    const upd = () => {
      const s = parseISO(a.value), e = parseISO(b.value);
      out.textContent = s && e && e > s ? out.dataset.days.replace("{n}", Math.round((e - s) / 864e5).toLocaleString("en-US")) : "";
    };
    a.addEventListener("change", upd); b.addEventListener("change", upd); upd();
  });
});

// القوائم المنسدلة: تستبدل <select> بقائمة عائمة مع علامة اختيار، وعناوين المجموعات، وبحث للقوائم الطويلة.
// العنصر الأصلي يبقى مخفيًا ومتزامنًا، فالنموذج يُرسل كما هو. data-native يُبقي القائمة الأصلية.
ENHANCERS.push((root) => {
  const CHEV = svg('<path d="M7 10l5 5 5-5"/>');
  const CHECK = svg('<path d="M5 12l5 5 9-10"/>');
  const esc = (t) => t.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  root.querySelectorAll("select:not([multiple]):not([data-native])").forEach((select) => {
    if (select.classList.contains("sel-native")) return;
    const wrap = document.createElement("div");
    wrap.className = "sel";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "sel-field";
    btn.setAttribute("aria-haspopup", "listbox");
    btn.setAttribute("aria-expanded", "false");
    btn.disabled = select.disabled;
    if (select.id) { const lbl = document.querySelector(`label[for="${select.id}"]`); if (lbl) { btn.id = `${select.id}_btn`; lbl.htmlFor = btn.id; } }
    if (select.getAttribute("aria-label")) btn.setAttribute("aria-label", select.getAttribute("aria-label"));
    select.before(wrap);
    wrap.append(btn, select);
    select.classList.add("sel-native");
    select.tabIndex = -1;
    const show = () => { const o = select.options[select.selectedIndex]; btn.innerHTML = `<span>${esc(o ? o.text : "")}</span>${CHEV}`; };
    show();
    select.addEventListener("change", show);

    btn.addEventListener("click", () => {
      if (Float.isOpenFor(btn)) return Float.close(true);
      const pop = document.createElement("div");
      pop.className = "sel-pop";
      const searchable = select.options.length > 8;
      pop.innerHTML = (searchable ? '<input class="sel-search" type="search" autocomplete="off">' : "") + '<div class="sel-list" role="listbox"></div>';
      const list = pop.querySelector(".sel-list"), search = pop.querySelector(".sel-search");
      const build = (q) => {
        let html = "", group = null;
        [...select.options].forEach((o, i) => {
          if (q && !o.text.toLowerCase().includes(q)) return;
          const g = o.parentElement.tagName === "OPTGROUP" ? o.parentElement.label : null;
          if (g !== group) { group = g; if (g) html += `<div class="sel-group">${esc(g)}</div>`; }
          html += `<button type="button" role="option" class="sel-opt${o.selected ? " on" : ""}" data-i="${i}" aria-selected="${o.selected}"${o.disabled ? " disabled" : ""}><span>${esc(o.text)}</span>${o.selected ? CHECK : ""}</button>`;
        });
        list.innerHTML = html || '<div class="sel-empty">—</div>';
      };
      const pick = (i) => { select.selectedIndex = i; select.dispatchEvent(new Event("change", { bubbles: true })); Float.close(true); };
      const move = (dir) => {
        const opts = [...list.querySelectorAll(".sel-opt:not(:disabled)")];
        const at = opts.indexOf(document.activeElement);
        const next = opts[Math.max(0, Math.min(opts.length - 1, at < 0 ? 0 : at + dir))];
        if (next) next.focus();
      };
      build("");
      pop.addEventListener("click", (e) => { const t = e.target.closest(".sel-opt"); if (t && !t.disabled) pick(Number(t.dataset.i)); });
      pop.addEventListener("keydown", (e) => {
        if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
        else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
        else if (e.key === "Enter" && e.target === search) { e.preventDefault(); const f = list.querySelector(".sel-opt:not(:disabled)"); if (f) pick(Number(f.dataset.i)); }
      });
      if (search) search.addEventListener("input", () => { build(search.value.trim().toLowerCase()); Float.place(); });
      Float.open(btn, pop);
      if (search) search.focus({ preventScroll: true });
      else (list.querySelector(".sel-opt.on") || list.querySelector(".sel-opt"))?.focus({ preventScroll: true });
    });
    btn.addEventListener("keydown", (e) => { if ((e.key === "ArrowDown" || e.key === "ArrowUp") && !Float.isOpenFor(btn)) { e.preventDefault(); btn.click(); } });
  });
});

// رفع الملفات: زر بلغة الصفحة بدل عنصر المتصفح (الذي يكتب "No file chosen" بالإنجليزية)
ENHANCERS.push((root) => {
  root.querySelectorAll('input[type="file"]:not(.file-native)').forEach((input) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn file-pick";
    const label = input.dataset.choose || "…";
    btn.innerHTML = `${svg('<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>')}<span>${label}</span>`;
    input.classList.add("file-native");
    input.before(btn);
    btn.addEventListener("click", () => input.click());
    if (input.id) { const lbl = document.querySelector(`label[for="${input.id}"]`); if (lbl) { btn.id = `${input.id}_btn`; lbl.htmlFor = btn.id; } }
    input.addEventListener("change", () => {
      const f = input.files && input.files[0];
      btn.querySelector("span").textContent = f ? f.name : label;
      btn.classList.toggle("chosen", !!f);
    });
  });
});

// قائمة تُظهر مجموعة واحدة حسب اختيارها: <select data-shows="x"> ومجموعات <div data-group="x" data-value="...">
// (مثل ممثلي الجهة المختارة في أطراف المشروع). بدون JavaScript تظهر كل المجموعات والخادم يتحقق.
ENHANCERS.push((root) => {
  root.querySelectorAll("select[data-shows]").forEach((sel) => {
    const groups = root.querySelectorAll(`[data-group="${sel.dataset.shows}"]`);
    const sync = () => groups.forEach((g) => {
      g.hidden = g.dataset.value !== sel.value;
      g.querySelectorAll("input, select, textarea").forEach((f) => { f.disabled = g.hidden; });
    });
    sel.addEventListener("change", sync);
    sync();
  });
});

enhance(document);
