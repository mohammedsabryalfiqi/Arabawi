/* العرباوي — واجهة التعرف على الخطوط العربية */
const $ = (s) => document.querySelector(s);

const AR_DIGITS = "٠١٢٣٤٥٦٧٨٩";
const arNum = (n) => String(n).replace(/\d/g, (d) => AR_DIGITS[d]);

let lastFile = null;
let lastResult = null;

/* ---------------- الصحة والتخزين والمكتبة ---------------- */
async function refreshHealth() {
  try {
    const r = await fetch("/api/health");
    const j = await r.json();
    $("#healthPill").textContent = j.ok ? "الخادم متصل" : "غير متصل";
  } catch {
    $("#healthPill").textContent = "غير متصل";
  }
}

async function refreshStorage() {
  const s = await (await fetch("/api/storage")).json();
  const pct = Math.min(100, (s.used_bytes / s.quota_bytes) * 100);
  $("#meterFill").style.width = pct.toFixed(2) + "%";
  $("#meterTxt").textContent =
    `المستخدم ${s.used_gb} ج.ب من حصة ${s.quota_gb} ج.ب (متبقي ${s.free_gb} ج.ب) · ` +
    `حرّ القرص ${s.disk_free_gb} ج.ب · ${arNum(s.font_count)} خطًا مفهرسًا`;
  $("#storageTag").textContent = `حصة التخزين ${arNum(s.quota_gb)} جيجابايت`;
}

async function refreshFonts() {
  const fonts = await (await fetch("/api/fonts")).json();
  const box = $("#fontTable");
  if (!fonts.length) {
    box.innerHTML = `<div class="muted">لا خطوط بعد — أضف خطًا أو شغّل tools/fetch_demo_fonts.py</div>`;
    return;
  }
  box.innerHTML = fonts.map((f) => `
    <div class="frow">
      <div><b>${esc(f.name)}</b> <span class="muted">${esc(f.family || "")} ${esc(f.style || "")}</span></div>
      <span class="badge">تغطية عربية ${arNum(Math.round((f.analysis?.coverage || 0) * 100))}٪</span>
      <span class="badge">${esc(f.license || "")} · ${esc(f.source || "")}</span>
      <button class="del" data-id="${f.id}">حذف</button>
    </div>`).join("");
  box.querySelectorAll(".del").forEach((b) =>
    b.onclick = async () => {
      await fetch("/api/fonts/" + b.dataset.id, { method: "DELETE" });
      refreshFonts(); refreshStorage();
    });
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

/* ---------------- التعرف ---------------- */
async function identify(file, textOverride) {
  const fd = new FormData();
  fd.append("file", file);
  if (textOverride) fd.append("text", textOverride);
  const r = await fetch("/api/identify", { method: "POST", body: fd });
  if (!r.ok) throw new Error((await r.json()).detail || "فشل التحليل");
  return await r.json();
}

function renderResult(res) {
  lastResult = res;
  $("#work").hidden = false;
  $("#origImg").src = res.original_url + "?t=" + Date.now();
  $("#enhImg").src = res.enhanced_url + "?t=" + Date.now();

  const chips = [
    `عدد الكلمات: ${arNum(res.word_count)}`,
    `عدد الأسطر (الجمل): ${arNum(res.line_count)}`,
  ];
  if (res.ocr) chips.push(`التعرف الضوئي: ثقة ${arNum(Math.round(res.ocr.confidence * 100))}٪`);
  else chips.push("التعرف الضوئي: غير متوفر — أدخل النص يدويًا");
  if (res.fonts_in_library === 0) chips.push("المكتبة فارغة!");
  $("#metaChips").innerHTML = chips.map((c, i) =>
    `<span class="chip ${i === 2 ? (res.ocr ? "ok" : "bad") : ""}">${esc(c)}</span>`).join("");

  if (!$("#textInput").value || textWasFromOcr) {
    $("#textInput").value = res.text_used || "";
    textWasFromOcr = true;
  }
  $("#ocrHint").textContent = res.needs_text
    ? "لم يتوفر نص: اكتب جملة الصورة كاملة (كلمة أو أكثر) ثم اضغط «طابِق الخط»."
    : "يمكنك تصحيح النص ثم إعادة المطابقة — عدد الكلمات يُستخدم لضبط تقسيم الجملة بلا تجزئة للحروف.";

  const box = $("#results");
  if (!res.matches?.length) {
    box.innerHTML = `<div class="muted">لا نتائج بعد — أدخل نص الجملة وطابِق.</div>`;
    return;
  }
  box.innerHTML = res.matches.map((m) => `
    <div class="row ${m.rank === 1 ? "first" : ""}">
      <div class="rank">${arNum(String(m.rank).padStart(2, "0"))}</div>
      <div>
        <div class="rname">${esc(m.name)}</div>
        <div class="rbadges">
          <span class="badge">${esc(m.license)}</span>
          <span class="badge">${esc(m.source)}</span>
          ${m.style && m.style !== "Regular" ? `<span class="badge">${esc(m.style)}</span>` : ""}
        </div>
      </div>
      <div class="conf">
        <b>${arNum(m.confidence)}٪</b>
        <div class="bar"><i style="width:${m.confidence}%"></i></div>
      </div>
      ${m.preview_url ? `<div class="preview-img"><img src="${m.preview_url}" alt="${esc(m.name)}"></div>` : ""}
      <div class="wordscores">تشابه الكلمات: ${m.word_scores.map((w) => arNum(Math.round(w * 100)) + "٪").join(" · ")}</div>
    </div>`).join("");
}

let textWasFromOcr = true;
$("#textInput").addEventListener("input", () => { textWasFromOcr = false; });

async function runIdentify(textOverride) {
  if (!lastFile) return;
  $("#matchBtn").disabled = true;
  $("#matchBtn").textContent = "جارٍ التحليل…";
  try {
    const res = await identify(lastFile, textOverride);
    renderResult(res);
  } catch (e) {
    $("#results").innerHTML = `<div class="chip bad">${esc(e.message)}</div>`;
  } finally {
    $("#matchBtn").disabled = false;
    $("#matchBtn").textContent = "طابِق الخط";
  }
}

/* ---------------- الأحداث ---------------- */
const drop = $("#drop");
drop.onclick = () => $("#file").click();
drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = (e) => {
  e.preventDefault(); drop.classList.remove("over");
  if (e.dataTransfer.files?.length) handleFile(e.dataTransfer.files[0]);
};
$("#file").onchange = (e) => e.target.files.length && handleFile(e.target.files[0]);

function handleFile(f) {
  lastFile = f;
  textWasFromOcr = true;
  $("#textInput").value = "";
  runIdentify("");
}

$("#matchBtn").onclick = () => runIdentify($("#textInput").value.trim());

$("#fontForm").onsubmit = async (e) => {
  e.preventDefault();
  const f = $("#fontFile").files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("file", f);
  fd.append("name", $("#fontName").value);
  fd.append("license", $("#fontLicense").value);
  fd.append("source", $("#fontSource").value || "مكتبة المالك");
  const r = await fetch("/api/fonts", { method: "POST", body: fd });
  const j = await r.json();
  if (!r.ok) alert(j.detail || "فشل رفع الخط");
  else { $("#fontForm").reset(); refreshFonts(); refreshStorage(); }
};

refreshHealth(); refreshStorage(); refreshFonts();
setInterval(refreshHealth, 15000);
