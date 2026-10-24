// يُحمّل قبل رسم الصفحة (بدون defer) حتى لا يظهر وميض ولا تتحرك العناصر بعد ظهورها:
// 1) لون الخلفية الداكن يُرسم فورًا قبل وصول ملف التنسيق
(() => {
  const root = document.documentElement;
  root.style.colorScheme = "dark";
  root.style.backgroundColor = "#04051a";
  root.classList.add("js");
})();
