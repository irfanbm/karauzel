"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const HEADLINE_MAX = 8;
const BODY_MAX = 30;
const BRIEF_FIELDS = ["topic", "goal", "audience", "language", "tone", "slides", "cta_type", "handle", "cta_detail", "source"];
const LAST_PROJECT = "carouso:last-project";
const ROUTE = location.pathname.startsWith("/design") ? "design" : location.pathname.startsWith("/export") ? "export" : location.pathname.startsWith("/admin-dashboard") ? "admin-dashboard" : location.pathname.startsWith("/dashboard") ? "dashboard" : "brief";
const ROUTE_PATH = { brief: "/project/new", design: "/design", export: "/export", dashboard: "/dashboard", "admin-dashboard": "/admin-dashboard" };
if (location.pathname === "/") location.replace("/dashboard");

const state = { catalog: null, project: { id: null, slides: [] }, dirty: false, saving: null, busy: true, draggedSlide: null };

// ---------- helpers ----------
let toastTimer;
let lastError = "";
function copyText(text) {
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(text);
  const area = document.createElement("textarea");
  area.value = text;
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.append(area);
  area.select();
  document.execCommand("copy");
  area.remove();
  return Promise.resolve();
}

function readableError(error, context = "") {
  const raw = String(error?.message || error || "Terjadi kesalahan.");
  if (/failed to fetch|networkerror|load failed/i.test(raw)) {
    return `${context ? `${context}: ` : ""}Tidak bisa terhubung ke server Carouso. Pastikan jendela start.bat masih terbuka, lalu klik Coba lagi.`;
  }
  return raw;
}

function showError(message, context = "") {
  lastError = readableError(message, context);
  toast(lastError, true);
  return lastError;
}

function toast(message, isError = false, persistent = false) {
  const el = $("#toast");
  el.classList.toggle("progress", persistent);
  const text = $("#toast-message");
  const copy = $(".toast-copy", el);
  if (text) text.textContent = message;
  else el.textContent = message;
  el.classList.toggle("error", isError);
  el.classList.add("show");
  if (copy) copy.hidden = !isError;
  clearTimeout(toastTimer);
  if (!persistent) toastTimer = setTimeout(() => { el.classList.remove("show", "progress"); if (copy) copy.hidden = true; }, isError ? 10000 : 2500);
}

async function api(path, options = {}) {
  const init = { method: options.method || "GET", headers: {} };
  if (options.json !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.json);
  } else if (options.body !== undefined) {
    init.body = options.body;
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    throw new Error(readableError(error, `${init.method} ${path}`));
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || data.message || `Permintaan gagal (${response.status})`);
  return data;
}

const words = (text) => (text.trim() ? text.trim().split(/\s+/).length : 0);
const roleLabel = (role) => state.catalog?.roles[role]?.label || role;
const imageUrl = (name) => `/api/projects/${state.project.id}/images/${name}`;

function setSaveState(text) {
  const el = $("#save-state");
  el.textContent = text;
  el.dataset.state = text.toLowerCase().includes("gagal") ? "error" : text.toLowerCase().includes("menyimpan") ? "saving" : "saved";
}

// ---------- brief <-> form ----------
function readBrief() {
  const brief = {};
  for (const name of BRIEF_FIELDS) brief[name] = $(`#${name}`).value;
  brief.slides = Number(brief.slides) || 6;
  brief.structure = $("input[name=structure]:checked")?.value || "auto";
  return brief;
}

function writeBrief(brief) {
  for (const name of BRIEF_FIELDS) if (brief[name] !== undefined) $(`#${name}`).value = brief[name];
  const radio = $(`input[name=structure][value="${brief.structure}"]`);
  if (radio) radio.checked = true;
  $("#source").closest("details").open = Boolean(brief.source);
}

// ---------- structure picker + flow ----------
function renderStructures() {
  const box = $("#structures");
  box.innerHTML = "";
  for (const [key, spec] of Object.entries(state.catalog.structures)) {
    const label = document.createElement("label");
    label.className = "structure";
    label.innerHTML = `<input type="radio" name="structure" value="${key}"><strong></strong><small></small>`;
    $("strong", label).textContent = spec.label;
    $("small", label).textContent = spec.description;
    box.append(label);
  }
  $("input[name=structure]", box).checked = true;
}

async function updateFlow() {
  const brief = readBrief();
  if (brief.structure === "auto") {
    $("#flow").innerHTML = "Alur: <b>Hook</b> → AI menentukan isinya → <b>CTA</b>";
    return;
  }
  try {
    const { roles } = await api(`/api/outline?structure=${brief.structure}&slides=${brief.slides}`);
    $("#flow").innerHTML = "Alur: " + roles.map((role) => `<b>${roleLabel(role)}</b>`).join(" → ");
  } catch {
    $("#flow").textContent = "";
  }
}

// ---------- slide cards ----------
function newSlide(role = "point") {
  const bytes = crypto.getRandomValues(new Uint8Array(4));
  const id = [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
    return { id, role, headline: "", body: "", bullets: [], image: null, images: [], locked: false, notes: "" };
}

function autosize(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = `${textarea.scrollHeight + 2}px`;
}

function updateCounts(card, slide) {
  const h = words(slide.headline);
  const b = words(slide.body);
  const hc = $('.wc[data-for="headline"]', card);
  const bc = $('.wc[data-for="body"]', card);
  hc.textContent = `${h}/${HEADLINE_MAX} kata`;
  bc.textContent = `${b}/${BODY_MAX} kata`;
  hc.classList.toggle("over", h > HEADLINE_MAX);
  bc.classList.toggle("over", b > BODY_MAX);
}

const DESIGN_FONTS = ["system", "serif", "mono", "display"];
function escapeHtml(value) { return String(value).replace(/[&<>\"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" })[char]); }
const DESIGN_LAYOUTS = [
  { id: "editorial", name: "Editorial stack", hint: "Headline dominan, banyak ruang", mark: "Aa" },
  { id: "split", name: "Split statement", hint: "Teks dan panel berimbang", mark: "1|2" },
  { id: "poster", name: "Poster note", hint: "Satu pesan, satu pukulan", mark: "01" },
  { id: "custom", name: "Tulis sendiri", hint: "Jelaskan layout dengan kata-kata", mark: "+" },
];
const DESIGN_TYPES = [
  { id: "ai-recommendation", name: "AI rekomendasi", hint: "Dipilih sesuai style dan isi konten", sample: "AI", font: "var(--font)" },
  { id: "serif-contrast", name: "Fraunces + Satoshi", hint: "Display serif / body sans", sample: "Aa", font: "Georgia, serif" },
  { id: "grotesk-clean", name: "Clash + General Sans", hint: "Display grotesk / body sans", sample: "Aa", font: "system-ui, sans-serif" },
  { id: "mono-technical", name: "Space Grotesk + Mono", hint: "Display tegas / body teknikal", sample: "01", font: "Consolas, monospace" },
  { id: "serif-editorial", name: "DM Serif + Lora", hint: "Serif display / serif body", sample: "Aa", font: "Georgia, serif" },
  { id: "sans-brutalist", name: "Space Grotesk + Work Sans", hint: "Kontras sans yang kuat", sample: "Ag", font: "system-ui, sans-serif" },
  { id: "serif-modern", name: "Canela + Inter", hint: "Serif modern / sans netral", sample: "Aa", font: "Georgia, serif" },
  { id: "sans-geometric", name: "General Sans + Jakarta", hint: "Geometris / humanis", sample: "Ag", font: "system-ui, sans-serif" },
  { id: "mono-classic", name: "Playfair + Plex Mono", hint: "Editorial tech", sample: "01", font: "Georgia, serif" },
];
const DESIGN_PALETTES = [
  { id: "paper", name: "Paper / Ink", colors: { bg: "#f4efe4", text: "#20211d", accent: "#b8452a" } },
  { id: "clay", name: "Clay / Moss", colors: { bg: "#e9dccb", text: "#2f3a2c", accent: "#a4563a" } },
  { id: "night", name: "Night / Citrus", colors: { bg: "#1c1f1b", text: "#f2ecdd", accent: "#d6e05a" } },
  { id: "custom", name: "Custom", colors: null },
];
const GOOGLE_FONT_URLS = [
  "https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,500;9..144,600;9..144,700&family=Inter:wght@300;400;500;600;700&family=IBM+Plex+Mono:ital,wght@0,300;0,400;0,500;1,300&family=JetBrains+Mono:wght@300;400;500;700&family=Lora:ital,wght@0,400;0,500;0,600;1,400&family=Manrope:wght@300;400;500;600;700;800&family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=Space+Grotesk:wght@300;400;500;700&family=Space+Mono:wght@400;700&family=Work+Sans:wght@300;400;500;600&display=swap",
];
function ensureGoogleFonts() {
  GOOGLE_FONT_URLS.forEach((href) => { if (!document.querySelector(`link[href="${href}"]`)) { const link = document.createElement("link"); link.rel = "stylesheet"; link.href = href; document.head.append(link); } });
}
const DESIGN_RATIOS = [
  { id: "4:5", name: "Feed", hint: "1080 x 1350" },
  { id: "1:1", name: "Square", hint: "1080 x 1080" },
  { id: "9:16", name: "Story", hint: "1080 x 1920" },
];

const CHROME_DEFAULTS = { page_indicator: true, indicator_location: "footer", indicator_type: "number", first_header: true, first_footer: true, header_category: true, header_divider: true, header_title: true, footer_brand: true };

function renderChromeControls() {
  const root = $("#chrome-controls");
  const settings = designState().chrome;
  root.replaceChildren();
  const groups = [
    ["Umum", [["page_indicator", "Indikator halaman"], ["indicator_location", "Lokasi indikator", ["footer", "header"]], ["indicator_type", "Jenis indikator", ["number", "dot", "line", "bar"]], ["first_header", "Header di slide pertama"], ["first_footer", "Footer di slide pertama"]]],
    ["Header", [["header_category", "Kategori slide"], ["header_divider", "Garis pembatas"], ["header_title", "Judul carousel"]]],
    ["Footer", [["footer_brand", "Watermark / brand"]]],
  ];
  groups.forEach(([title, fields]) => {
    const group = document.createElement("fieldset");
    const legend = document.createElement("legend");
    legend.textContent = title;
    group.append(legend);
    fields.forEach(([key, text, options]) => {
      const label = document.createElement("label");
      const input = document.createElement(options ? "select" : "input");
      if (options) options.forEach((value) => { const option = document.createElement("option"); option.value = value; option.textContent = value; input.append(option); });
      else input.type = "checkbox";
      if (options) input.value = settings[key]; else input.checked = settings[key];
      input.addEventListener("change", () => { designState().chrome[key] = options ? input.value : input.checked; markDirty(); renderCarouselPreview(); });
      label.append(input, document.createTextNode(` ${text}`));
      group.append(label);
    });
    root.append(group);
  });
}

function designState() {
  const current = state.project.design || {};
  state.project.design = {
    mode: "custom", layout: "editorial", layout_custom: "", pairing: "serif-contrast", ratio: "4:5", palette: "paper",
    references: [], reference_points: [], reference_summary: "",
    ...current,
    chrome: { ...CHROME_DEFAULTS, ...(current.chrome || {}) },
    palette_custom: { bg: "#f4efe4", text: "#20211d", accent: "#b8452a", ...(current.palette_custom || {}) },
  };
  if (!Array.isArray(state.project.design.references)) state.project.design.references = [];
  if (!Array.isArray(state.project.design.reference_points)) state.project.design.reference_points = [];
  return state.project.design;
}

function setDesign(key, value) {
  designState()[key] = value;
  markDirty();
  renderLayoutStudio();
}

function optionGroup(root, items, current, key, build) {
  root.replaceChildren();
  items.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `design-option${current === item.id ? " selected" : ""}`;
    button.setAttribute("aria-pressed", String(current === item.id));
    button.innerHTML = build(item);
    button.addEventListener("click", () => setDesign(key, item.id));
    root.append(button);
  });
}

function hexToRgb(hex) { return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)); }
function luminance(hex) {
  const [r, g, b] = hexToRgb(hex).map((c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrastRatio(a, b) { const [x, y] = [luminance(a), luminance(b)].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05); }

function renderContrastNote() {
  const { bg, text, accent } = designState().palette_custom;
  const body = contrastRatio(bg, text);
  const acc = contrastRatio(bg, accent);
  const parts = [`Teks ${body.toFixed(1)}:1 ${body >= 4.5 ? "terbaca" : "terlalu lemah, akan dikoreksi"}`, `Aksen ${acc.toFixed(1)}:1 ${acc >= 3 ? "terbaca" : "terlalu pucat, akan digelapkan"}`];
  const note = $("#contrast-note");
  note.textContent = parts.join(" · ");
  note.classList.toggle("warn", body < 4.5 || acc < 3);
}

function renderLayoutStudio() {
  renderChromeControls();
  const design = designState();
  $$(".layout-mode").forEach((tab) => { const active = tab.dataset.layoutMode === design.mode; tab.classList.toggle("active", active); tab.setAttribute("aria-selected", String(active)); });
  $("#mode-custom").hidden = design.mode !== "custom";
  $("#mode-reference").hidden = design.mode !== "reference";
  optionGroup($("#layout-recipes"), DESIGN_LAYOUTS, design.layout, "layout", (item) => `<span class="recipe-mark">${item.mark}</span><span><strong>${item.name}</strong><small>${item.hint}</small></span>`);
  optionGroup($("#type-options"), DESIGN_TYPES, design.pairing, "pairing", (item) => `<span class="type-sample" style="font-family:${item.font}">${item.sample}</span><span><strong>${item.name}</strong><small>${item.hint}</small></span>`);
  optionGroup($("#ratio-options"), DESIGN_RATIOS, design.ratio, "ratio", (item) => `<span class="ratio-shape r-${item.id.replace(":", "-")}"></span><span><strong>${item.id} · ${item.name}</strong><small>${item.hint}</small></span>`);
  optionGroup($("#palette-options"), DESIGN_PALETTES, design.palette, "palette", (item) => {
    const colors = item.colors || design.palette_custom;
    return `<span class="swatches">${["bg", "text", "accent"].map((key) => `<i style="background:${colors[key]}"></i>`).join("")}</span><span><strong>${item.name}</strong>${item.colors ? "" : "<small>Pilih warna sendiri</small>"}</span>`;
  });
  $("#layout-custom-box").hidden = design.layout !== "custom";
  if (document.activeElement !== $("#layout-custom")) $("#layout-custom").value = design.layout_custom;
  $("#palette-custom-box").hidden = design.palette !== "custom";
  $$("[data-color]").forEach((input) => { input.value = design.palette_custom[input.dataset.color]; });
  $$("[data-color-code]").forEach((code) => { code.textContent = design.palette_custom[code.dataset.colorCode]; });
  renderContrastNote();
  renderReferences();
  renderReferencePoints();
  $("#generate-mode-note").textContent = "";
  const needsReference = design.mode === "reference" && !design.reference_points.length;
  $("#generate-design").disabled = needsReference;
}

$$(".layout-mode").forEach((tab) => tab.addEventListener("click", () => setDesign("mode", tab.dataset.layoutMode)));
$("#layout-custom").addEventListener("input", (event) => { designState().layout_custom = event.target.value; markDirty(); });
$$("[data-color]").forEach((input) => input.addEventListener("input", () => {
  designState().palette_custom[input.dataset.color] = input.value;
  $(`[data-color-code="${input.dataset.color}"]`).textContent = input.value;
  const swatch = $$("#palette-options .design-option")[3];
  if (swatch) $$(".swatches i", swatch).forEach((dot, i) => { dot.style.background = designState().palette_custom[["bg", "text", "accent"][i]]; });
  renderContrastNote();
  markDirty();
}));

function renderReferences() {
  const list = $("#reference-list");
  const refs = designState().references;
  list.replaceChildren();
  refs.forEach((ref, index) => {
    const item = document.createElement("li");
    item.className = "reference-item";
    const thumb = ref.type === "image" ? `<img src="${imageUrl(ref.value)}" alt="">` : `<span class="ref-link" aria-hidden="true">↗</span>`;
    item.innerHTML = `${thumb}<span class="ref-text">${escapeHtml(ref.type === "image" ? "Gambar referensi" : ref.value)}</span><button type="button" class="icon" aria-label="Hapus referensi">×</button>`;
    $("button", item).addEventListener("click", () => { refs.splice(index, 1); markDirty(); renderReferences(); });
    list.append(item);
  });
  $("#reference-empty").hidden = refs.length > 0;
  $("#reference-add-row").hidden = refs.length >= 6;
  $("#analyze-reference").disabled = refs.length === 0;
}

function addReference(ref) {
  const refs = designState().references;
  if (refs.length >= 6) return toast("Maksimal 6 referensi.");
  refs.push(ref);
  markDirty();
  renderReferences();
}

$("#reference-url-add").addEventListener("click", () => {
  const input = $("#reference-url");
  const value = input.value.trim();
  if (!/^https?:\/\/\S+$/i.test(value)) return toast("Masukkan link yang diawali http:// atau https://", true);
  addReference({ type: "link", value });
  input.value = "";
});
$("#reference-url").addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); $("#reference-url-add").click(); } });
$("#reference-file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  event.target.value = "";
  if (!file) return;
  try {
    await ensureProject();
    const { image } = await api(`/api/projects/${state.project.id}/images`, { method: "POST", body: file });
    addReference({ type: "image", value: image });
  } catch (error) {
    showError(error, "Upload referensi");
  }
});

function renderReferencePoints() {
  const design = designState();
  const points = design.reference_points;
  $("#reference-result").hidden = points.length === 0;
  if (!points.length) return;
  $("#reference-summary").textContent = design.reference_summary;
  const root = $("#reference-points");
  if (root.contains(document.activeElement)) return;
  root.replaceChildren();
  const groups = [...new Set(points.map((point) => point.group))];
  groups.forEach((group) => {
    const box = document.createElement("fieldset");
    box.className = "point-group";
    box.innerHTML = `<legend>${escapeHtml(group)}</legend>`;
    points.forEach((point, index) => {
      if (point.group !== group) return;
      const row = document.createElement("div");
      row.className = `point-row${point.use ? "" : " off"}`;
      const id = `point-${index}`;
      let control = "";
      if (point.kind === "color") control = `<span class="point-color"><input type="color" id="${id}" value="${point.value}"><code>${point.value}</code></span>`;
      else if (point.kind === "choice") control = `<select id="${id}">${point.options.map((option) => `<option value="${option.value}"${option.value === point.value ? " selected" : ""}>${escapeHtml(option.label)}</option>`).join("")}</select>`;
      else control = `<input type="text" id="${id}" maxlength="60" value="${escapeHtml(point.value)}" placeholder="@handle">`;
      row.innerHTML = `<label class="point-use"><input type="checkbox"${point.use ? " checked" : ""} aria-label="Pakai ${escapeHtml(point.label)}"></label><label class="point-label" for="${id}"><strong>${escapeHtml(point.label)}</strong><small>${escapeHtml(point.why)}</small></label>${control}`;
      $(".point-use input", row).addEventListener("change", (event) => { point.use = event.target.checked; row.classList.toggle("off", !point.use); markDirty(); });
      const input = $(`#${id}`, row);
      input.addEventListener("input", () => { point.value = input.value; const code = $("code", row); if (code) code.textContent = input.value; markDirty(); });
      box.append(row);
    });
    root.append(box);
  });
}

$("#analyze-reference").addEventListener("click", async () => {
  const button = $("#analyze-reference");
  const status = $("#analyze-state");
  button.disabled = true;
  button.textContent = "Menganalisa…";
  status.textContent = "Membaca warna, huruf, dan komposisi referensi.";
  try {
    await ensureProject();
    const result = await api(`/api/projects/${state.project.id}/design/analyze`, { method: "POST", json: snapshot() });
    state.project.design = result.project.design;
    status.textContent = result.source === "ai" ? "Dianalisa dengan AI." : "Dianalisa dari warna dan struktur referensi.";
    renderLayoutStudio();
  } catch (error) {
    status.textContent = "";
    showError(error, "Analisa referensi");
  } finally {
    button.disabled = designState().references.length === 0;
    button.textContent = "Analisa referensi";
  }
});

const RATIO_SIZE = { "4:5": [1080, 1350], "1:1": [1080, 1080], "9:16": [1080, 1920] };

function slideHtml(slide, plan, tokens, index, total) {
  const headline = richTextHtml(partsFor(slide, "headline"));
  const body = slide.body ? richTextHtml(partsFor(slide, "body")) : "";
  const number = String(index + 1).padStart(2, "0");
  const bullets = (slide.bullets || []).slice(0, 5).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const image = slide.images?.[0] ? `<div class="ds-media" style="background-image:url('${imageUrl(slide.images[0])}')"></div>` : `<div class="ds-media ds-media-solid"><span>${number}</span></div>`;
  const chrome = designState().chrome;
  const visibility = (visible) => visible ? "" : ' style="visibility:hidden" aria-hidden="true"';
  const indicator = chrome.indicator_type === "number" ? `${number} / ${String(total).padStart(2, "0")}` : chrome.indicator_type === "bar" ? `<i style="width:${(index + 1) / total * 100}%"></i>` : Array.from({ length: total }, (_, i) => `<i${i === index ? ' class="active"' : ""}></i>`).join("");
  const page = `<span class="chrome-indicator chrome-${chrome.indicator_type}" aria-label="${index + 1} / ${total}"${visibility(chrome.page_indicator)}>${indicator}</span>`;
  const footerHandle = `<span${visibility(chrome.footer_brand && tokens.footer.includes("handle"))}>${escapeHtml(tokens.footer_text || "")}</span>`;
  const footer = `<footer class="ds-footer"${visibility(index !== 0 || chrome.first_footer)}>${footerHandle}${chrome.indicator_location === "footer" ? page : "<span></span>"}</footer>`;
  const topic = state.project.brief?.topic || state.project.title || "Carousel";
  const header = `<header class="ds-header" style="${index === 0 && !chrome.first_header ? "visibility:hidden;" : ""}${!chrome.header_divider ? "border-bottom-color:transparent;" : ""}"><span${visibility(chrome.header_title)}>${escapeHtml(topic)}</span><span class="chrome-header-end"><span class="slide-category"${visibility(chrome.header_category)}>${escapeHtml(roleLabel(slide.role))}</span>${chrome.indicator_location === "header" ? page : ""}</span></header>`;
  const kicker = `<span class="ds-kicker">${escapeHtml(roleLabel(slide.role))}</span>`;
  let inner;
  switch (plan.pattern) {
    case "cover-split":
      inner = `${image}<div class="ds-copy">${kicker}<h2 class="ds-h">${headline}</h2>${body ? `<p class="ds-b">${body}</p>` : ""}</div>`;
      break;
    case "split-panel":
      inner = `<div class="ds-copy">${tokens.decoration === "number" ? `<span class="ds-num">${number}</span>` : kicker}<h2 class="ds-h">${headline}</h2>${body ? `<p class="ds-b">${body}</p>` : ""}</div>${image}`;
      break;
    case "numbered":
      inner = `<div class="ds-copy"><span class="ds-num">${number}</span><h2 class="ds-h">${headline}</h2>${body ? `<p class="ds-b">${body}</p>` : ""}</div>`;
      break;
    case "list":
      inner = `<div class="ds-copy">${kicker}<h2 class="ds-h">${headline}</h2>${bullets ? `<ol class="ds-list">${bullets}</ol>` : body ? `<p class="ds-b">${body}</p>` : ""}</div>`;
      break;
    case "quote":
      inner = `<div class="ds-copy"><span class="ds-mark" aria-hidden="true">“</span><h2 class="ds-h">${headline}</h2>${body ? `<p class="ds-b">${body}</p>` : ""}</div>`;
      break;
    case "cta":
      inner = `<div class="ds-copy">${kicker}<h2 class="ds-h">${headline}</h2>${body ? `<p class="ds-b">${body}</p>` : ""}${tokens.footer_text ? `<span class="ds-cta">${escapeHtml(tokens.footer_text)}</span>` : ""}</div>`;
      break;
      case "ui-metric":
       inner = `<div class="ds-ui-metric"><span class="ds-kicker">${escapeHtml(roleLabel(slide.role))}</span><h2 class="ds-h">${headline}</h2>${body ? `<p class="ds-b">${body}</p>` : ""}</div>`;
      break;
    case "ui-feed":
       inner = `<div class="ds-ui-feed"><span class="ds-kicker">${escapeHtml(roleLabel(slide.role))}</span><h2 class="ds-h">${headline}</h2>${bullets ? `<ol class="ds-list">${bullets}</ol>` : body ? `<p class="ds-b">${body}</p>` : ""}</div>`;
      break;
    case "ui-editorial":
       inner = `<div class="ds-ui-editorial"><span class="ds-kicker">${escapeHtml(roleLabel(slide.role))}</span><h2 class="ds-h">${headline}</h2>${body ? `<p class="ds-b">${body}</p>` : ""}</div>`;
      break;
    case "cover-type":
      inner = `<div class="ds-copy">${kicker}<h2 class="ds-h">${headline}</h2>${body ? `<p class="ds-b">${body}</p>` : ""}</div>`;
      break;
    default:
      inner = `<div class="ds-copy">${kicker}<h2 class="ds-h">${headline}</h2>${body ? `<p class="ds-b">${body}</p>` : ""}</div>`;
  }
  const selected = designState().body_template || "auto";
  const template = selected === "auto" ? index === 0 ? "hero" : slide.role === "cta" ? "closing" : "editorial" : selected;
  const simpleSvg = `<svg class="ds-simple-visual" viewBox="0 0 240 160" role="img" aria-label="Ilustrasi sederhana"><rect x="24" y="30" width="192" height="100" rx="14" fill="none" stroke="${tokens.accent}" stroke-width="5"/><path d="M48 102l38-34 28 22 30-40 48 52" fill="none" stroke="${tokens.accent}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/><circle cx="178" cy="55" r="9" fill="${tokens.accent}"/></svg>`;
  const visual = slide.images?.[0] ? `<div class="ds-body-visual ds-user-visual" style="background-image:url('${imageUrl(slide.images[0])}')"></div>` : (slide.role === "solution" || slide.role === "point" || slide.role === "proof") ? `<div class="ds-body-visual">${simpleSvg}</div>` : "";
  return `<div class="ds-artboard">${header}<section class="ds-content reviewed-body ds-pattern-${plan.pattern}" data-template="${template}"><div class="ds-inner">${inner}${visual}</div></section>${footer}</div>`;
}

function renderCarouselPreview() {
  ensureGoogleFonts();
  if (!$("#body-template-choice")) {
    const label = document.createElement("label");
    label.textContent = "Template body ";
    const select = document.createElement("select");
    select.id = "body-template-choice";
    Object.entries({ auto: "Otomatis: Hero / Editorial / Closing", hero: "Hero", editorial: "Editorial", closing: "Closing" }).forEach(([value, text]) => select.add(new Option(text, value)));
    select.addEventListener("change", () => { designState().body_template = select.value; markDirty(); renderCarouselPreview(); });
    label.append(select);
    $("#carousel-preview").before(label);
  }
  $("#body-template-choice").value = designState().body_template || "auto";
  const root = $("#carousel-preview");
  if (!root) return;
  const result = state.project.design?.result;
  root.replaceChildren();
  $("#design-notes").replaceChildren();
  $("#preview-empty").hidden = Boolean(result);
  $("#regenerate-design").hidden = !result;
  $("#preview-meta").textContent = "";
  if (!result) return;
  const tokens = result.tokens;
  const slides = state.project.slides || [];
  const plans = result.slides.filter((plan) => slides.some((slide) => slide.id === plan.id));
  const [width, height] = RATIO_SIZE[tokens.ratio] || RATIO_SIZE["4:5"];
  const scale = 300 / width;
  plans.forEach((plan, index) => {
    const slide = slides.find((item) => item.id === plan.id);
    const frame = document.createElement("div");
    frame.className = "ds-frame";
    frame.style.width = `${width * scale}px`;
    frame.style.height = `${height * scale}px`;
    const article = document.createElement("article");
    article.className = ["ds-slide", `ds-p-${plan.pattern}`, `ds-mode-${plan.mode}`, `ds-l-${tokens.layout}`, `ds-ratio-${String(tokens.ratio || "4:5").replace(":", "-")}`, `ds-pair-${tokens.pairing || "serif-contrast"}`, `ds-case-${tokens.case}`, `ds-w-${tokens.weight}`, `ds-s-${tokens.scale}`, `ds-a-${tokens.align}`, `ds-d-${tokens.density}`, `ds-o-${tokens.decoration}`].join(" ");
    const vars = plan.mode === "invert" ? { bg: tokens.text, text: tokens.bg, muted: tokens.muted, accent: tokens.accent, "on-accent": tokens.on_accent, "display-font": tokens.display_font_css || "Georgia, serif", "body-font": tokens.body_font_css || "system-ui, sans-serif", "display-weight": tokens.display_weight || 600, "body-weight": tokens.body_weight || 400, "display-spacing": tokens.display_spacing || "-.04em", "body-spacing": tokens.body_spacing || "0", "display-line-height": tokens.display_line_height || 1, "body-line-height": tokens.body_line_height || 1.5 } : { bg: tokens.bg, text: tokens.text, muted: tokens.muted, accent: tokens.accent, "on-accent": tokens.on_accent, "display-font": tokens.display_font_css || "Georgia, serif", "body-font": tokens.body_font_css || "system-ui, sans-serif", "display-weight": tokens.display_weight || 600, "body-weight": tokens.body_weight || 400, "display-spacing": tokens.display_spacing || "-.04em", "body-spacing": tokens.body_spacing || "0", "display-line-height": tokens.display_line_height || 1, "body-line-height": tokens.body_line_height || 1.5 };
    Object.entries(vars).forEach(([key, value]) => article.style.setProperty(`--ds-${key}`, value));
    article.style.setProperty("--canvas-width", `${width}px`);
    article.style.width = `${width}px`;
article.style.height = `${height}px`;
     article.style.setProperty("--fit", plan.fit || "0.68");
     article.style.setProperty("--content-load", plan.load || "0");
     article.style.transform = `scale(${scale})`;
    article.innerHTML = slideHtml(slide, plan, tokens, index, plans.length);
    frame.append(article);
    root.append(frame);
  });
  const when = result.generated ? new Date(result.generated).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" }) : "";
  $("#preview-meta").textContent = `${plans.length} slide · ${tokens.ratio} · ${result.source === "ai" ? "disusun AI" : "disusun aturan sistem"}${when ? ` · ${when}` : ""}`;
  (result.notes || []).forEach((note) => { const item = document.createElement("li"); item.textContent = note; $("#design-notes").append(item); });
  document.fonts.ready.then(() => {
    if (!root.isConnected || !root.offsetWidth) return;
    root.querySelectorAll(".reviewed-body").forEach((body) => {
      if (body.scrollHeight > body.clientHeight + 2) {
        const warning = document.createElement("li");
        warning.textContent = "Konten melebihi area body. Pendekkan teks atau pecah slide; ukuran font tidak diperkecil otomatis.";
        $("#design-notes").append(warning);
      }
    });
  });
}

function openDesignTab(name) {
  $$(".design-tab").forEach((item) => { const active = item.dataset.designTab === name; item.classList.toggle("active", active); item.setAttribute("aria-selected", String(active)); });
  $$(".design-view").forEach((view) => { const active = view.id === `design-${name}`; view.classList.toggle("active", active); view.hidden = !active; });
  hideFormatBar();
  if (name === "preview") renderCarouselPreview();
}

async function generateDesign(button) {
  const design = designState();
  if (design.mode === "reference" && !design.reference_points.length) {
    toast("Analisa referensi dulu, atau pindah ke Racik sendiri.", true);
    return;
  }
  const buttons = [$("#generate-design"), $("#regenerate-design")];
  buttons.forEach((item) => { item.disabled = true; });
  const label = button.textContent;
  button.textContent = "Menyusun desain…";
  $("#design-loading").hidden = false;
  $("#design-loading-label").textContent = "Mengukur canvas dan menyusun proporsi…";
  document.body.classList.add("design-is-loading");
  try {
    await ensureProject();
    const saved = await api(`/api/projects/${state.project.id}/design/generate`, { method: "POST", json: snapshot() });
    state.project.design = saved.design;
    state.dirty = false;
    setSaveState("Tersimpan");
    openDesignTab("preview");
    $("#design-preview").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showError(error, "Generate desain");
  } finally {
    buttons.forEach((item) => { item.disabled = false; });
    button.textContent = label;
    $("#design-loading").hidden = true;
    document.body.classList.remove("design-is-loading");
  }
}

function plainParts(text) {
  return text ? [{ text, bold: "0", italic: "0", underline: "0", important: "", font: "" }] : [];
}

function partsFor(slide, field) {
  const rich = slide[`${field}_rich`];
  const plain = slide[field] || "";
  if (Array.isArray(rich) && rich.length && rich.map((part) => part.text).join("") === plain) return rich.map((part) => ({ ...part }));
  return plainParts(plain);
}

function richTextHtml(parts) {
  return parts.map((part) => {
    const classes = [`rich-${DESIGN_FONTS.includes(part.font) ? part.font : "system"}`];
    if (part.bold === "1") classes.push("rich-b");
    if (part.italic === "1") classes.push("rich-i");
    if (part.underline === "1") classes.push("rich-u");
    if (part.important) classes.push(`rich-important-${part.important}`);
    return `<span class="${classes.join(" ")}">${escapeHtml(part.text)}</span>`;
  }).join("");
}

function applyStyle(parts, start, end, key, value) {
  const chars = [];
  parts.forEach((part) => [...part.text].forEach((char) => chars.push({ ...part, text: char })));
  if (key !== "font" && value === "toggle") value = chars.slice(start, end).every((char) => char[key] === "1") ? "0" : "1";
  for (let i = start; i < end && i < chars.length; i += 1) chars[i][key] = value;
  return chars.reduce((merged, char) => {
    const last = merged[merged.length - 1];
    if (last && last.bold === char.bold && last.italic === char.italic && last.underline === char.underline && last.important === char.important && last.font === char.font) last.text += char.text;
    else merged.push({ ...char });
    return merged;
  }, []);
}

let formatTarget = null;

function offsetsIn(element, range) {
  const before = document.createRange();
  before.selectNodeContents(element);
  before.setEnd(range.startContainer, range.startOffset);
  const start = [...before.toString()].length;
  return { start, end: start + [...range.toString()].length };
}

function restoreSelection(element, start, end) {
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  const range = document.createRange();
  let count = 0;
  let node;
  let startSet = false;
  while ((node = walker.nextNode())) {
    const length = [...node.textContent].length;
    if (!startSet && start <= count + length) { range.setStart(node, [...node.textContent].slice(0, start - count).join("").length); startSet = true; }
    if (startSet && end <= count + length) { range.setEnd(node, [...node.textContent].slice(0, end - count).join("").length); break; }
    count += length;
  }
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
}

function hideFormatBar() {
  $("#format-float").hidden = true;
  formatTarget = null;
}

function updateFormatBar() {
  if (ROUTE !== "design") return;
  const bar = $("#format-float");
  if (bar.contains(document.activeElement)) return;
  const selection = window.getSelection();
  if (!selection?.rangeCount || selection.isCollapsed) return hideFormatBar();
  const range = selection.getRangeAt(0);
  const host = range.commonAncestorContainer.nodeType === Node.TEXT_NODE ? range.commonAncestorContainer.parentElement : range.commonAncestorContainer;
  const field = host?.closest?.(".rich-text");
  if (!field || !field.contains(range.startContainer) || !field.contains(range.endContainer)) return hideFormatBar();
  const { start, end } = offsetsIn(field, range);
  if (end <= start) return hideFormatBar();
  formatTarget = { slideId: field.dataset.slide, field: field.dataset.field, start, end };
  const slide = state.project.slides.find((item) => item.id === formatTarget.slideId);
  const chars = [];
  partsFor(slide, formatTarget.field).forEach((part) => [...part.text].forEach(() => chars.push(part)));
  const selected = chars.slice(start, end);
  ["bold", "italic", "underline"].forEach((key) => $(`[data-format="${key}"]`, bar).classList.toggle("on", selected.every((char) => char[key] === "1")));
  $("#format-important").value = selected.length && new Set(selected.map((char) => char.important || "")).size === 1 ? (selected[0].important || "") : "";
  const fonts = new Set(selected.map((char) => char.font));
  $("#format-font").value = fonts.size === 1 ? [...fonts][0] : "";
  bar.hidden = false;
  const rect = range.getBoundingClientRect();
  const width = bar.offsetWidth;
  const left = Math.min(Math.max(8, rect.left + rect.width / 2 - width / 2), window.innerWidth - width - 8);
  const top = rect.top - bar.offsetHeight - 10 < 8 ? rect.bottom + 10 : rect.top - bar.offsetHeight - 10;
  bar.style.left = `${left}px`;
  bar.style.top = `${top}px`;
}

function applyFormat(key, value) {
  if (!formatTarget) return;
  const { slideId, field, start, end } = formatTarget;
  const slide = state.project.slides.find((item) => item.id === slideId);
  if (!slide) return;
  slide[`${field}_rich`] = applyStyle(partsFor(slide, field), start, end, key, value);
  markDirty();
  const element = $(`.rich-text[data-slide="${slideId}"][data-field="${field}"]`);
  element.innerHTML = richTextHtml(slide[`${field}_rich`]);
  restoreSelection(element, start, end);
  formatTarget = { slideId, field, start, end };
  updateFormatBar();
}

document.addEventListener("selectionchange", updateFormatBar);
window.addEventListener("scroll", () => { if (!$("#format-float").hidden) updateFormatBar(); }, true);
$("#format-float").addEventListener("mousedown", (event) => { if (!event.target.closest("select")) event.preventDefault(); });
$$("#format-float [data-format]").forEach((button) => button.addEventListener("click", () => applyFormat(button.dataset.format, "toggle")));
$("#format-important").addEventListener("change", (event) => {
  if (event.target.value !== undefined) applyFormat("important", event.target.value);
});
$("#format-font").addEventListener("change", (event) => {
  const target = formatTarget;
  if (event.target.value) applyFormat("font", event.target.value);
  else if (target) formatTarget = target;
});
$("#format-clear").addEventListener("click", () => {
  if (!formatTarget) return;
  ["bold", "italic", "underline"].forEach((key) => applyFormat(key, "0"));
  applyFormat("font", "");
});
document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !$("#format-float").hidden) { window.getSelection()?.removeAllRanges(); hideFormatBar(); } });

function renderDesign() {
  renderLayoutStudio();
  renderCarouselPreview();
  const root = $("#design-cards");
  root.replaceChildren();
  const slides = state.project.slides || [];
  $("#content-empty").hidden = slides.some((slide) => slide.headline || slide.body);
  slides.forEach((slide, index) => {
    if (!slide.headline && !slide.body) return;
    const card = document.createElement("article");
    card.className = "design-card";
    const block = (field, label) => slide[field] ? `<span class="field-label">${label}</span><div class="rich-text rich-${field}" data-slide="${slide.id}" data-field="${field}">${richTextHtml(partsFor(slide, field))}</div>` : "";
    card.innerHTML = `<div class="design-card-head"><span class="num">${String(index + 1).padStart(2, "0")}</span><strong>${escapeHtml(roleLabel(slide.role))}</strong><span class="lock-note">Terkunci · ubah di Brief</span></div>${block("headline", "Judul")}${block("body", "Isi")}`;
    root.append(card);
  });
}

$$(".design-tab").forEach((tab) => tab.addEventListener("click", () => openDesignTab(tab.dataset.designTab)));
$("#generate-design").addEventListener("click", (event) => generateDesign(event.currentTarget));
$("#regenerate-design").addEventListener("click", (event) => generateDesign(event.currentTarget));


function renderRoute() {
  const mode = ROUTE;
  $("#design-panel").hidden = mode !== "design";
  $("#export-panel").hidden = mode !== "export";
  $("#dashboard-panel").hidden = mode !== "dashboard";
  $("#admin-dashboard-panel")?.toggleAttribute("hidden", mode !== "admin-dashboard");
  $$(".brief-only").forEach((element) => { element.hidden = mode !== "brief"; });
  document.body.dataset.route = mode;
  const home = $("#brand-home");
  if (home) home.href = mode === "admin-dashboard" ? "/admin-dashboard" : "/dashboard";
  $$(".progress-step").forEach((step) => {
    const active = step.dataset.route === ROUTE_PATH[mode];
    step.classList.toggle("active", active);
    step.toggleAttribute("aria-current", active);
  });
  const slides = state.project.slides || [];
  $("#export-summary").textContent = slides.length ? `${slides.length} slide dari Brief sudah dimuat. UI export akan dibangun dari nol.` : "Belum ada project. Mulai dari Brief dulu.";
  if (mode === "design") renderDesign();
  if (mode === "export") renderExport();
}

function renderExport() {
  renderCarouselPreview();
  const source = $("#carousel-preview");
  const target = $("#export-preview");
  if (!source || !target) return;
  target.innerHTML = source.innerHTML;
  const frames = target.querySelectorAll(".ds-frame");
  frames.forEach((frame) => { frame.style.transform = "none"; frame.style.margin = "0 0 24px"; });
  $("#export-summary").textContent = frames.length ? `${frames.length} slide siap disimpan.` : "Generate desain terlebih dahulu.";
}

function downloadBlob(blob, filename) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

function rendererCss() {
  return [...document.styleSheets].flatMap((sheet) => { try { return [...sheet.cssRules].map((rule) => rule.cssText); } catch { return []; } }).join("\n");
}

$("#download-html")?.addEventListener("click", () => {
  const content = $("#export-preview")?.innerHTML || $("#carousel-preview")?.innerHTML || "";
  const html = `<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Carouso export</title><style>${rendererCss()}</style></head><body><main class="carousel-export">${content}</main></body></html>`;
  downloadBlob(new Blob([html], { type: "text/html" }), `${state.project.id || "carouso"}.html`);
});

$("#download-png")?.addEventListener("click", async () => {
  const frame = $("#export-preview .ds-frame") || $("#carousel-preview .ds-frame");
  if (!frame) return;
  const canvas = document.createElement("canvas");
  canvas.width = 1080; canvas.height = Math.round(1080 * (RATIO_SIZE[designState().ratio || "4:5"][1] / RATIO_SIZE[designState().ratio || "4:5"][0]));
  const article = frame.querySelector("article");
  if (!article) return;
  const clone = article.cloneNode(true);
  clone.style.transform = "none";
  clone.style.width = `${canvas.width}px`;
  clone.style.height = `${canvas.height}px`;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${canvas.width}" height="${canvas.height}"><foreignObject width="100%" height="100%" xmlns="http://www.w3.org/1999/xhtml"><style>${rendererCss()}</style>${clone.outerHTML}</foreignObject></svg>`;
  const image = new Image();
  image.onload = () => { canvas.getContext("2d").drawImage(image, 0, 0); canvas.toBlob((blob) => downloadBlob(blob, `${state.project.id || "carouso"}-01.png`), "image/png"); };
  image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
});

function renderMiniPreview(slides) {
  const preview = $("#mini-preview-list");
  preview.replaceChildren();
  slides.forEach((slide, index) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "mini-slide";
    item.title = `Lompat ke slide ${index + 1}`;
    item.innerHTML = `<b>${String(index + 1).padStart(2, "0")}</b><span></span>`;
    $("span", item).textContent = slide.headline || roleLabel(slide.role);
    item.addEventListener("click", () => $(`.slide-card[data-id="${slide.id}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" }));
    preview.append(item);
  });
}

function renderSlides() {
  const list = $("#slide-list");
  const slides = state.project?.slides || [];
  list.innerHTML = "";
  const roleOptions = Object.entries(state.catalog.roles);
  slides.forEach((slide, index) => {
    const card = $("#slide-template").content.firstElementChild.cloneNode(true);
    card.dataset.id = slide.id;
    card.draggable = true;
    card.classList.toggle("locked", slide.locked);
    card.addEventListener("dragstart", () => { state.draggedSlide = slide; card.classList.add("dragging"); });
    card.addEventListener("dragend", () => { state.draggedSlide = null; card.classList.remove("dragging"); });
    card.addEventListener("dragover", (event) => { event.preventDefault(); card.classList.add("drag-over"); });
    card.addEventListener("dragleave", () => card.classList.remove("drag-over"));
    card.addEventListener("drop", (event) => {
      event.preventDefault();
      card.classList.remove("drag-over");
      if (!state.draggedSlide || state.draggedSlide === slide) return;
      const from = slides.indexOf(state.draggedSlide);
      const to = slides.indexOf(slide);
      slides.splice(from, 1);
      slides.splice(to, 0, state.draggedSlide);
      renderSlides();
      markDirty();
    });
    $(".num", card).textContent = String(index + 1).padStart(2, "0");

    const role = $(".role", card);
    const roleId = `role-${slide.id}`;
    role.id = roleId;
    $(".card-top label", card).htmlFor = roleId;
    for (const [key, spec] of roleOptions) role.add(new Option(spec.label, key, false, key === slide.role));
    role.title = state.catalog.roles[slide.role]?.hint || "";

    const headline = $(".headline", card);
    const options = $(".headline-options", card);
    options.replaceChildren();
    const headlineOptions = Array.isArray(slide.headline_options) ? slide.headline_options.slice(0, 2) : [];
    options.hidden = index !== 0 || headlineOptions.length === 0;
    headlineOptions.forEach((option, optionIndex) => {
      const label = document.createElement("label");
      label.className = "headline-option";
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = `headline-choice-${slide.id}`;
      radio.checked = slide.headline === option;
      radio.setAttribute("aria-label", `Pilih opsi judul ${optionIndex + 2}`);
      radio.addEventListener("change", () => {
        if (!radio.checked) return;
        slide.headline = option;
        headline.value = option;
        updateCounts(card, slide);
        markDirty();
      });
      const text = document.createElement("span");
      text.textContent = option;
      label.append(radio, text);
      options.append(label);
    });
    const body = $(".body", card);
    const bullets = $(".bullets", card);
    headline.value = slide.headline;
    body.value = slide.body;
    bullets.value = slide.bullets.join("\n");
    headline.setAttribute("aria-label", `Judul slide ${index + 1}`);
    body.setAttribute("aria-label", `Isi slide ${index + 1}`);
    bullets.setAttribute("aria-label", `Poin-poin slide ${index + 1}`);
    if (headline.placeholder) headline.placeholder = state.catalog.roles[slide.role]?.hint || "Judul slide";

    const note = $(".note", card);
    note.hidden = !slide.notes;
    note.textContent = slide.notes;

    const lock = $('[data-action="lock"]', card);
    lock.setAttribute("aria-pressed", String(slide.locked));
    lock.setAttribute("aria-label", slide.locked ? "Buka kunci slide" : "Kunci slide");
    $('[data-action="up"]', card).disabled = index === 0;
    $('[data-action="down"]', card).disabled = index === slides.length - 1;
    $('[data-action="regen"]', card).disabled = slide.locked;

    const imageBtn = $(".image-btn", card);
    const images = Array.isArray(slide.images) && slide.images.length ? slide.images : (slide.image ? [slide.image] : []);
    slide.images = images.slice(0, 4);
    slide.image = slide.images[0] || null;
    const gallery = $(".image-gallery", card);
    gallery.replaceChildren();
    slide.images.forEach((image, imageIndex) => {
      const thumb = document.createElement("button");
      thumb.type = "button";
      thumb.className = "image-thumb";
      thumb.style.backgroundImage = `url("${imageUrl(image)}")`;
      thumb.setAttribute("aria-label", `Hapus gambar ${imageIndex + 1}`);
      thumb.title = "Hapus gambar ini";
      thumb.addEventListener("click", () => {
        slide.images.splice(imageIndex, 1);
        slide.image = slide.images[0] || null;
        renderSlides();
        markDirty();
      });
      gallery.append(thumb);
    });
    imageBtn.classList.toggle("filled", slide.images.length > 0);
    imageBtn.disabled = slide.images.length >= 4;
    imageBtn.style.backgroundImage = "";
    imageBtn.setAttribute("aria-label", slide.images.length >= 4 ? "Maksimal 4 gambar" : "Tambah gambar");
    $(".remove-image", card).hidden = slide.images.length === 0;

    updateCounts(card, slide);
    list.append(card);
    [headline, body, bullets].forEach(autosize);
  });
  $("#slide-count").textContent = slides.length ? `${slides.length} slide` : "";
  $("#add-slide").disabled = slides.length >= (state.catalog?.max_slides || 12);
  $("#empty").classList.toggle("is-hidden", slides.length > 0 || ROUTE !== "brief");
  renderMiniPreview(slides);
}

function slideFor(element) {
  const id = element.closest(".slide-card")?.dataset.id;
  return state.project.slides.find((slide) => slide.id === id);
}

$("#slide-list").addEventListener("input", (event) => {
  const slide = slideFor(event.target);
  if (!slide) return;
  const card = event.target.closest(".slide-card");
  if (event.target.matches(".headline")) {
    slide.headline = event.target.value;
    slide.headline_options = [];
    $(".headline-options", card).hidden = true;
  }
  if (event.target.matches(".body")) slide.body = event.target.value;
  if (event.target.matches(".bullets")) slide.bullets = event.target.value.split("\n").map((s) => s.trim()).filter(Boolean);
  if (event.target.matches("textarea")) autosize(event.target);
  card.classList.remove("has-error");
  updateCounts(card, slide);
  markDirty();
});

$("#slide-list").addEventListener("change", (event) => {
  if (!event.target.matches(".role")) return;
  slideFor(event.target).role = event.target.value;
  event.target.title = state.catalog.roles[event.target.value]?.hint || "";
  markDirty();
});

$("#slide-list").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const slides = state.project.slides;
  const slide = slideFor(button);
  const index = slides.indexOf(slide);
  const action = button.dataset.action;
  if (action === "up" || action === "down") {
    const target = action === "up" ? index - 1 : index + 1;
    [slides[index], slides[target]] = [slides[target], slides[index]];
    renderSlides();
    $(`.slide-card[data-id="${slide.id}"] [data-action="${action}"]`)?.focus();
  } else if (action === "lock") {
    slide.locked = !slide.locked;
    renderSlides();
    $(`.slide-card[data-id="${slide.id}"] [data-action="lock"]`).focus();
  } else if (action === "delete") {
    if (slides.length <= 3) return toast("Minimal 3 slide.", true);
    if ((slide.headline || slide.body) && !confirm(`Hapus slide ${index + 1}?`)) return;
    slides.splice(index, 1);
    renderSlides();
  } else if (action === "regen") {
    if (!(await confirmRegenerate(slide))) return;
    return regenerateSlide(slide);
  } else if (action === "image") {
    return openImageDialog(slide);
  } else if (action === "remove-image") {
    slide.image = null;
    slide.images = [];
    renderSlides();
  }
  markDirty();
});

$("#add-slide").addEventListener("click", () => {
  const slides = state.project.slides;
  const slide = newSlide("point");
  slides.push(slide);
  renderSlides();
  markDirty();
  $(`.slide-card[data-id="${slide.id}"] .headline`).focus();
});

// ---------- project lifecycle ----------
// state.project always exists. id === null means it only lives in the browser so far.
let creating = null;
function ensureProject() {
  if (state.project.id) return Promise.resolve(state.project);
  creating ??= createProject().finally(() => { creating = null; });
  return creating;
}

async function createProject() {
  const slides = state.project.slides;
  const created = await api("/api/projects", { method: "POST", json: { brief: readBrief() } });
  state.project = { ...created, slides };
  await api(`/api/projects/${created.id}`, { method: "PUT", json: snapshot() });
  localStorage.setItem(LAST_PROJECT, created.id);
  await refreshProjects();
  setSaveState("Tersimpan");
  return state.project;
}

function snapshot() {
  return { ...state.project, brief: readBrief() };
}

let saveTimer;
function markDirty() {
  if (!state.project.id) {
    if ($("#topic").value.trim()) ensureProject().catch((error) => showError(error, "Autosave"));
    return;
  }
  state.dirty = true;
  setSaveState("Belum tersimpan");
  clearTimeout(saveTimer);
  saveTimer = setTimeout(save, 800);
}

async function save() {
  if (!state.project.id || !state.dirty) return;
  clearTimeout(saveTimer);
  state.dirty = false;
  setSaveState("Menyimpan…");
  try {
    const saved = await api(`/api/projects/${state.project.id}`, { method: "PUT", json: snapshot() });
    state.project.updated = saved.updated;
    if (!state.dirty) setSaveState("Tersimpan");
  } catch (error) {
    state.dirty = true;
    setSaveState("Gagal menyimpan");
    toast(`Gagal menyimpan: ${error.message}`, true);
  }
}

async function openProject(id) {
  await save();
  try {
    state.project = await api(`/api/projects/${id}`);
  } catch {
    localStorage.removeItem(LAST_PROJECT);
    return;
  }
  localStorage.setItem(LAST_PROJECT, id);
  writeBrief(state.project.brief);
  $(".project-trigger-label").textContent = state.project.brief?.topic || "Project";
  renderSlides();
  renderRoute();
  updateFlow();
  setSaveState("Tersimpan");
  $("#issues").innerHTML = "";
}

async function startNew() {
  await save();
  state.project = { id: null, slides: [] };
  $("#brief").reset();
  renderStructures();
  writeBrief({ slides: 6, structure: "auto", language: "Bahasa Indonesia" });
  $(".project-trigger-label").textContent = "Project baru";
  await showOutline();
  updateFlow();
  setSaveState("");
  localStorage.removeItem(LAST_PROJECT);
  $("#issues").innerHTML = "";
}

function projectStatus(item) {
  if (item.status) return item.status;
  return "Brief";
}

function formatProjectDate(value) {
  if (!value) return "Belum disimpan";
  try { return new Intl.DateTimeFormat("id-ID", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); } catch { return value; }
}

async function refreshProjects() {
  const list = $("#project-list");
  const items = await api("/api/projects").catch(() => []);
  list.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "project-empty";
    empty.textContent = "Belum ada project tersimpan.";
    list.append(empty);
    return;
  }
  for (const item of items) {
    const row = document.createElement("article");
    row.className = "project-item";
    if (item.id === state.project?.id) row.classList.add("active");
    row.innerHTML = `<div class="project-item-copy"><strong></strong><small></small></div><span class="project-status"></span><button class="project-open" type="button">Buka</button>`;
    $("strong", row).textContent = item.topic || "Tanpa topik";
    $("small", row).textContent = formatProjectDate(item.updated);
    $(".project-status", row).textContent = projectStatus(item);
    $(".project-open", row).addEventListener("click", async () => {
      await openProject(item.id);
      $("#project-dialog").close();
    });
    list.append(row);
  }
}

$("#project-trigger").addEventListener("click", async () => {
  await refreshProjects();
  $("#project-dialog").showModal();
  $("#project-trigger").setAttribute("aria-expanded", "true");
});
$("#close-projects").addEventListener("click", () => $("#project-dialog").close());
$("#project-dialog").addEventListener("close", () => $("#project-trigger").setAttribute("aria-expanded", "false"));
$("#new-project").addEventListener("click", async () => {
  await startNew();
  $("#project-dialog").close();
});

// An empty outline that follows the chosen structure, so people can also write by hand.
// It is only rebuilt while nothing has been written yet, so it never wipes real work.
async function showOutline() {
  const touched = state.project.slides.some((slide) => slide.headline || slide.body || slide.image);
  if (touched) return;
  const brief = readBrief();
  const structure = brief.structure === "auto" ? "listicle" : brief.structure;
  try {
    const { roles } = await api(`/api/outline?structure=${structure}&slides=${brief.slides}`);
    state.project.slides = roles.map((role) => newSlide(role));
    renderSlides();
  } catch {
    /* keep current outline */
  }
}

function onShapeChange() {
  updateFlow();
  showOutline().then(() => { updateCountHint(); markDirty(); });
}

$("#brief").addEventListener("input", (event) => {
  if (event.target.id === "topic") validateTopic(false);
  if (event.target.id === "slides") return onShapeChange();
  if (event.target.name !== "structure") markDirty();
});
$("#brief").addEventListener("change", (event) => {
  if (event.target.name === "structure") onShapeChange();
  if (event.target.id === "slides") {
    const input = event.target;
    const value = Math.round(Number(input.value));
    const clamped = Number.isFinite(value) && input.value !== "" ? Math.min(12, Math.max(3, value)) : 6;
    if (String(clamped) !== input.value) {
      input.value = clamped;
      toast(`Jumlah slide diatur ke ${clamped} (3–12).`);
      onShapeChange();
    }
  }
});

function updateCountHint() {
  const wanted = readBrief().slides;
  const have = state.project.slides.length;
  const hint = $("#generate-hint");
  if (hasContent() && wanted !== have && !state.busy) {
    hint.textContent = `Saat ini ${have} slide. Klik "Buat ulang isi slide" untuk membuat ${wanted} slide.`;
  } else if (hint.textContent.startsWith("Saat ini")) {
    hint.textContent = "";
  }
}

function validateTopic(focus = true) {
  const topic = $("#topic");
  const empty = !topic.value.trim();
  topic.setAttribute("aria-invalid", String(empty));
  topic.setAttribute("aria-describedby", empty ? "topic-error" : "");
  $("#topic-error").hidden = !empty;
  if (empty && focus) topic.focus();
  return !empty;
}

// ---------- generate ----------
function confirmRegenerate(slide) {
  const dialog = $("#regenerate-dialog");
  $("#regenerate-message").textContent = `Slide “${slide.headline || roleLabel(slide.role)}” akan dibuat ulang berdasarkan brief, struktur, dan referensi yang tersedia.`;
  dialog.showModal();
  return new Promise((resolve) => dialog.addEventListener("close", () => resolve(dialog.returnValue === "default"), { once: true }));
}

function showGenerationProgress(label) {
  const steps = [
    `${label} · membaca brief dan struktur carousel…`,
    `${label} · menyusun sudut pandang dan alur…`,
    `${label} · mengecek referensi yang tersedia…`,
    `${label} · merapikan copy agar siap diedit…`,
  ];
  let index = 0;
  toast(steps[index], false, true);
  const timer = setInterval(() => { index = Math.min(index + 1, steps.length - 1); toast(steps[index], false, true); }, 1800);
  return () => { clearInterval(timer); $("#toast").classList.remove("progress"); };
}

function setBusy(busy, label) {
  state.busy = busy;
  const button = $("#generate");
  button.disabled = busy;
  button.textContent = busy ? label : (hasContent() ? "Buat ulang isi slide" : "Buat isi slide");
  $("#next").disabled = busy;
}

const hasContent = () => Boolean(state.project?.slides.some((slide) => slide.headline));

$("#generate").addEventListener("click", async () => {
  if (state.busy || !validateTopic()) return;
  const unlocked = state.project?.slides.filter((s) => !s.locked && (s.headline || s.body)).length || 0;
  if (unlocked && !confirm(`${unlocked} slide yang tidak dikunci akan ditulis ulang. Lanjutkan?\n\nKunci slide yang ingin dipertahankan.`)) return;
  setBusy(true, "Menulis isi slide…");
  const stopProgress = showGenerationProgress("Menyusun isi slide");
  $("#generate-hint").textContent = "Biasanya 5–15 detik.";
  try {
    await ensureProject();
    const project = await api(`/api/projects/${state.project.id}/generate`, { method: "POST", json: snapshot() });
    state.project = project;
    state.dirty = false;
    renderSlides();
    setSaveState("Tersimpan");
    stopProgress();
    toast("Isi slide siap. Silakan edit.");
    $("#generate-hint").textContent = "Klik teks mana pun untuk mengedit.";
    $(".slide-card .headline")?.focus();
  } catch (error) {
    $("#generate-hint").textContent = "";
    const message = showError(error, "Generate isi slide");
    if (/belum diatur/i.test(message)) openSettings();
  } finally {
    setBusy(false);
  }
});

async function regenerateSlide(slide) {
  if (state.busy) return;
  if (!validateTopic()) return;
  const card = $(`.slide-card[data-id="${slide.id}"]`);
  card.classList.add("busy");
  state.busy = true;
  const stopProgress = showGenerationProgress("Membuat ulang slide");
  try {
    await ensureProject();
    const project = await api(`/api/projects/${state.project.id}/slides/${slide.id}/generate`, { method: "POST", json: snapshot() });
    state.project = project;
    state.dirty = false;
    renderSlides();
    setSaveState("Tersimpan");
    stopProgress();
    toast("Slide selesai dibuat ulang. Silakan review dan edit.");
    $(`.slide-card[data-id="${slide.id}"] .headline`)?.focus();
  } catch (error) {
    stopProgress();
    card.classList.remove("busy");
    showError(error, "Generate ulang slide");
  } finally {
    state.busy = false;
  }
}

// ---------- check + next ----------
function projectUrl(route) {
  return `${ROUTE_PATH[route]}?project=${state.project?.id || new URLSearchParams(location.search).get("project") || localStorage.getItem(LAST_PROJECT) || ""}`;
}

function switchMode(mode) {
  location.href = projectUrl(mode);
}

$("#back-to-brief").addEventListener("click", () => switchMode("brief"));
$("#back-to-design").addEventListener("click", () => switchMode("design"));
$("#continue-export")?.addEventListener("click", () => switchMode("export"));
$("#user-new-project")?.addEventListener("click", () => switchMode("brief"));
$("#user-start-brief")?.addEventListener("click", () => switchMode("brief"));
$$(".progress-step").forEach((step) => step.addEventListener("click", () => {
  const route = Object.keys(ROUTE_PATH).find((key) => ROUTE_PATH[key] === step.dataset.route);
  if (route) switchMode(route);
}));

$("#next").addEventListener("click", async () => {
  if (!validateTopic()) return;
  await ensureProject();
  const result = await api(`/api/projects/${state.project.id}/check`, { method: "POST", json: snapshot() });
  const list = $("#issues");
  list.innerHTML = "";
  $$(".slide-card").forEach((card) => card.classList.remove("has-error"));
  for (const issue of result.issues) {
    const li = document.createElement("li");
    li.className = issue.level;
    li.textContent = issue.message;
    list.append(li);
    if (issue.level === "error" && issue.slide) $$(".slide-card")[issue.slide - 1]?.classList.add("has-error");
  }
  if (!result.ok) {
    $(".slide-card.has-error .headline")?.focus();
    return toast("Masih ada slide yang perlu dilengkapi.", true);
  }
  const li = document.createElement("li");
  li.className = "ok";
  li.textContent = result.issues.length ? "Bisa lanjut. Periksa catatan di atas dulu." : "Brief lengkap.";
  list.append(li);
  toast("Brief lengkap. Membuka Design Studio.");
  location.href = projectUrl("design");
});

// ---------- images ----------
let imageTarget = null;
function openImageDialog(slide) {
  imageTarget = slide;
  $("#image-error").hidden = true;
  $("#image-url").value = "";
  $("#image-file").value = "";
  $("#image-dialog").showModal();
}

async function attachImage(request) {
  const error = $("#image-error");
  error.hidden = true;
  try {
    await ensureProject();
    if ((imageTarget.images || []).length >= 4) throw new Error("Maksimal 4 gambar per slide.");
    const { image } = await request();
    imageTarget.images = [...(imageTarget.images || []), image].slice(0, 4);
    imageTarget.image = imageTarget.images[0];
    $("#image-dialog").close();
    renderSlides();
    markDirty();
    toast("Gambar ditambahkan.");
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
  }
}

const uploadFile = (file) =>
  attachImage(() => api(`/api/projects/${state.project.id}/images`, { method: "POST", body: file }));

$("#image-file").addEventListener("change", (event) => {
  if (event.target.files[0]) uploadFile(event.target.files[0]);
});
$("#image-url-add").addEventListener("click", () => {
  const url = $("#image-url").value.trim();
  if (!url) return;
  attachImage(() => api(`/api/projects/${state.project.id}/images`, { method: "POST", json: { url } }));
});
const drop = $("#drop");
["dragenter", "dragover"].forEach((type) => drop.addEventListener(type, (event) => { event.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((type) => drop.addEventListener(type, () => drop.classList.remove("over")));
drop.addEventListener("drop", (event) => {
  event.preventDefault();
  const file = event.dataTransfer.files[0];
  if (file) uploadFile(file);
});
drop.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") { event.preventDefault(); $("#image-file").click(); }
});

// ---------- settings ----------
async function openSettings() {
  const config = await api("/api/config").catch(() => ({}));
  $("#provider").value = config.provider && config.provider !== "none" ? config.provider : "openai-compatible";
  $("#base-url").value = config.base_url || "";
  $("#model").value = config.model || "";
  $("#api-key").value = "";
  $("#api-key").placeholder = config.api_key ? "Tersimpan. Kosongkan untuk tetap memakai key lama." : "Tempel API key";
  $("#key-state").textContent = "";
  $("#send-images").checked = Boolean(config.send_images);
  $("#settings-dialog").showModal();
}

async function saveSettings() {
  await api("/api/config", {
    method: "POST",
    json: {
      provider: $("#provider").value,
      base_url: $("#base-url").value,
      model: $("#model").value,
      api_key: $("#api-key").value,
      send_images: $("#send-images").checked,
    },
  });
}

$("#settings").addEventListener("click", openSettings);
$("#theme-toggle").addEventListener("click", () => {
  const dark = document.body.classList.toggle("dark");
  $("#theme-toggle").setAttribute("aria-pressed", String(dark));
  $("#theme-toggle").setAttribute("aria-label", dark ? "Nonaktifkan dark mode" : "Aktifkan dark mode");
  localStorage.setItem("carouso:dark", dark ? "1" : "0");
});
if (localStorage.getItem("carouso:dark") === "1") {
  document.body.classList.add("dark");
  $("#theme-toggle").setAttribute("aria-pressed", "true");
  $("#theme-toggle").setAttribute("aria-label", "Nonaktifkan dark mode");
}
$("#save-provider").addEventListener("click", async () => {
  try {
    await saveSettings();
    $("#settings-dialog").close();
    toast("Pengaturan disimpan.");
  } catch (error) {
    showError(error, "Menyimpan pengaturan");
  }
});
$("#test-provider").addEventListener("click", async () => {
  const button = $("#test-provider");
  button.disabled = true;
  $("#key-state").textContent = "Mengetes…";
  try {
    await saveSettings();
    const result = await api("/api/config/test", { method: "POST" });
    $("#key-state").textContent = result.message;
  } catch (error) {
    $("#key-state").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

window.addEventListener("beforeunload", (event) => {
  if (state.dirty) { save(); event.preventDefault(); }
});

// ---------- boot ----------
const API_VERSION = 2;

function showFatal(title, detail) {
  lastError = `${title}\n${detail}`;
  $("#fatal-title").textContent = title;
  $("#fatal-detail").textContent = detail;
  $("#fatal").hidden = false;
  $$("main button, main input, main select, main textarea").forEach((el) => { el.disabled = true; });
}

async function serverReady() {
  let health;
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    if (response.status === 404) {
      showFatal("Server Carouso versi lama masih berjalan.",
        "Tutup semua jendela hitam Carouso, lalu jalankan start.bat lagi. Halaman ini akan termuat ulang otomatis.");
      return false;
    }
    health = await response.json();
  } catch {
    showFatal("Server Carouso tidak berjalan.", "Jalankan start.bat, lalu muat ulang halaman ini.");
    return false;
  }
  if (health.api !== API_VERSION) {
    showFatal("Versi server dan halaman berbeda.", "Tutup jendela Carouso, jalankan start.bat lagi, lalu muat ulang halaman ini.");
    return false;
  }
  return true;
}

function waitForServer() {
  const timer = setInterval(async () => {
    try {
      const response = await fetch("/api/health", { cache: "no-store" });
      if (response.ok && (await response.json()).api === API_VERSION) {
        clearInterval(timer);
        location.reload();
      }
    } catch { /* still down */ }
  }, 2000);
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy-error]");
  if (!button) return;
  const source = button.dataset.copyError;
  const text = source === "fatal" ? lastError : lastError || $("#toast-message")?.textContent || "";
  try {
    await copyText(text);
    const original = button.textContent;
    button.textContent = "Tersalin";
    setTimeout(() => { button.textContent = original; }, 1400);
  } catch {
    button.textContent = "Gagal menyalin";
  }
});

$("#retry-server").addEventListener("click", () => location.reload());

window.addEventListener("unhandledrejection", (event) => {
  event.preventDefault();
  showError(event.reason, "Aplikasi");
});

(async function init() {
  if (!(await serverReady())) return waitForServer();
  try {
    state.catalog = await api("/api/catalog");
  } catch (error) {
    showFatal("Gagal memuat Carouso.", readableError(error, "Memuat aplikasi"));
    return;
  }
  renderStructures();
  await refreshProjects();
  state.project = { id: null, slides: [] };
  const queryProject = new URLSearchParams(location.search).get("project");
  const last = queryProject || localStorage.getItem(LAST_PROJECT);
  if (last) await openProject(last);
  if (!state.project.id) await startNew();
  renderRoute();
  setBusy(false);
})();
