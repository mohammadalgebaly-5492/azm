document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-copy]");
  if (!b) return;
  const el = document.querySelector(b.dataset.copy);
  if (!el) return;
  const done = () => { const t = b.lastChild.textContent; b.lastChild.textContent = " تم النسخ"; setTimeout(() => (b.lastChild.textContent = t), 1800); };
  const fallback = () => { const r = document.createRange(); r.selectNodeContents(el); const s = getSelection(); s.removeAllRanges(); s.addRange(r); };
  if (navigator.clipboard) navigator.clipboard.writeText(el.textContent).then(done, fallback); else fallback();
});

// حساب الإجمالي أثناء الكتابة في نموذج البند (العرض فقط؛ الحساب المعتمد على الخادم)
(() => {
  const out = document.querySelector("output[data-calc]");
  if (!out) return;
  const [a, b] = out.dataset.calc.split(",").map((id) => document.getElementById(id));
  const num = (v) => parseFloat(String(v).replace(/[,٬\s]/g, "").replace(/[٠-٩]/g, (d) => "٠١٢٣٤٥٦٧٨٩".indexOf(d)).replace("٫", "."));
  const upd = () => {
    const q = num(a.value), r = num(b.value);
    out.textContent = isFinite(q) && isFinite(r) ? (Math.round(q * r * 100) / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—";
  };
  a.addEventListener("input", upd); b.addEventListener("input", upd);
})();
