// Fotobox – Logo, eigene Rahmen und Rahmen-Editor (Teil der Einstellungsseite, nutzt settings.js)
const ed = { layout: "single", key: null, custom: false, cell: [1800, 1200], pos: null, selected: null };
let hasLogo = false;
let logoAspect = 1;
let stickerNames = [];
let edTimer = null;

// Aktuelle (noch nicht gespeicherte) Formularwerte, damit Vorschauen sofort stimmen
function draft() {
  return {
    frame: $("frameInput").value,
    frame_text: $("titleInput").value,
    show_title: $("showTitle").checked,
    show_date: $("showDate").checked,
    logo: { enabled: $("logoEnabled").checked, position: $("logoPosition").value, size: Number($("logoSize").value) },
    edits: config.design.edits,
  };
}

// Formularwerte in config übernehmen (wie beim Speichern), bevor Teile neu aufgebaut werden
function syncForm() {
  document.querySelectorAll("[data-key]").forEach((el) => setPath(config, el.dataset.key, readInput(el)));
  config.design.layouts = [...document.querySelectorAll("#layoutChecks input:checked")].map((i) => i.value);
}

async function postImage(img, body) {
  const res = await fetch("/api/editor/preview.jpg", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) return;
  const old = img.src;
  img.src = URL.createObjectURL(await res.blob());
  if (old.startsWith("blob:")) URL.revokeObjectURL(old);
}

async function upload(url, form) {
  const res = await fetch(url, { method: "POST", body: form });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) throw new Error(data.error || `Fehler ${res.status}`);
  return data;
}

function editsFor(key) {
  config.design.edits = config.design.edits || {};
  return (config.design.edits[key] = config.design.edits[key] || {});
}

// ------------------------------------------------------------------ Logo
function refreshLogo() {
  const img = $("logoImg");
  img.hidden = !hasLogo;
  $("logoNone").hidden = hasLogo;
  $("logoDelete").disabled = !hasLogo;
  if (hasLogo) {
    img.onload = () => {
      logoAspect = img.naturalHeight / img.naturalWidth;
      renderElements();
    };
    img.src = `/uploads/logo.png?t=${Date.now()}`;
  }
}

async function uploadLogo() {
  const file = $("logoFile").files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  try {
    await upload("/api/logo", form);
    hasLogo = true;
    $("logoEnabled").checked = true;
    status($("logoStatus"), "✔ Logo hochgeladen – bitte speichern");
    refreshLogo();
    scheduleEditor();
  } catch (e) {
    status($("logoStatus"), `✖ ${e.message}`, false);
  }
  $("logoFile").value = "";
}

async function deleteLogo() {
  await fetch("/api/logo", { method: "DELETE" });
  hasLogo = false;
  $("logoEnabled").checked = false;
  refreshLogo();
  scheduleEditor();
}

// ------------------------------------------------------------------ Eigene Rahmen
function renderCustomList() {
  const box = $("customList");
  box.innerHTML = "";
  for (const c of config.design.custom_frames || []) {
    const item = document.createElement("div");
    item.className = "custom-item";
    item.innerHTML = `<img alt=""><strong></strong><span class="note"></span><button class="btn" type="button">Entfernen</button>`;
    item.querySelector("img").src = `/api/layouts/${c.id}/preview.jpg?w=400&t=${Date.now()}`;
    item.querySelector("strong").textContent = c.name;
    item.querySelector(".note").textContent = c.holes.length === 1 ? "1 Foto" : `${c.holes.length} Fotos`;
    item.querySelector("button").onclick = () => deleteCustom(c);
    box.appendChild(item);
  }
}

function applyServerConfig(saved) {
  syncForm();
  config.design.custom_frames = saved.design.custom_frames;
  config.design.layouts = saved.design.layouts;
  config.design.edits = saved.design.edits;
  layoutNames = layoutNames.filter(([id]) => !id.startsWith("custom-"))
    .concat(saved.design.custom_frames.map((c) => [c.id, c.name]));
  renderDesign();
  renderCustomList();
  fillLayoutSelect();
}

async function uploadCustom() {
  const file = $("customFile").files[0];
  if (!file) return status($("customStatus"), "Bitte zuerst eine PNG-Datei wählen.", false);
  const form = new FormData();
  form.append("file", file);
  form.append("name", $("customName").value);
  try {
    const r = await upload("/api/custom-frames", form);
    applyServerConfig(r.config);
    status($("customStatus"), `✔ «${r.frame.name}» mit ${r.frame.holes.length} Fotofenster(n) hinzugefügt`);
    $("customFile").value = "";
    $("customName").value = "";
  } catch (e) {
    status($("customStatus"), `✖ ${e.message}`, false);
  }
}

async function deleteCustom(c) {
  if (!confirm(`Rahmen «${c.name}» entfernen?`)) return;
  const res = await fetch(`/api/custom-frames/${c.id}`, { method: "DELETE" });
  applyServerConfig((await res.json()).config);
  if (ed.layout === c.id) {
    ed.layout = "single";
    $("edLayout").value = "single";
  }
  loadEditor();
}

// ------------------------------------------------------------------ Editor: Farben & Schrift
function fillLayoutSelect() {
  setOptions($("edLayout"), layoutNames, ed.layout);
}

function fillStyle(style) {
  const set = (name, value) => {
    const el = document.querySelector(`[data-style="${name}"]`);
    if (el.type === "checkbox") el.checked = !!value;
    else el.value = value;
  };
  const hex = (c) => (/^#[0-9a-f]{6}$/i.test(c || "") ? c : "#ffffff");
  set("base", hex(style.base));
  [0, 1, 2].forEach((i) => set(`accent${i}`, hex(style.accents[i] || style.base)));
  set("title_color", hex(style.title_color));
  set("subtitle_color", hex(style.subtitle_color));
  set("border", hex(style.border || "#ffffff"));
  set("no_border", !style.border);
  set("font", style.font);
  set("title_scale", style.title_scale);
  set("decor", style.decor);
  document.querySelector('[data-style="decor"]').closest("label").hidden = ed.custom || !style.has_decor;
  ed.style = style;
}

function readStyle(e) {
  const val = (name) => document.querySelector(`[data-style="${name}"]`);
  const edits = editsFor(ed.key);
  const name = e.target.dataset.style;
  if (name === "base") edits.base = val("base").value;
  if (name.startsWith("accent")) edits.accents = [0, 1, 2].map((i) => val(`accent${i}`).value);
  if (name === "title_color" || name === "subtitle_color") edits[name] = val(name).value;
  if (name === "border" || name === "no_border") edits.border = val("no_border").checked ? "" : val("border").value;
  if (name === "font") edits.font = val("font").value;
  if (name === "title_scale") edits.title_scale = Number(val("title_scale").value);
  if (name === "decor") edits.decor = val("decor").checked;
  ed.style = {
    ...ed.style,
    title_color: val("title_color").value,
    subtitle_color: val("subtitle_color").value,
    font: val("font").value,
  };
  renderElements();
  scheduleEditor(true);
}

// ------------------------------------------------------------------ Editor: Drag & Drop
function stageSize() {
  const r = $("edBg").getBoundingClientRect();
  return [r.width, r.height];
}

function savePositions() {
  const edits = editsFor(ed.key);
  edits.pos = edits.pos || {};
  edits.pos[ed.layout] = ed.pos;
}

function defaultLogoPos() {
  // wie auf dem Server: Ecke aus den Logo-Einstellungen
  const [cw, ch] = ed.cell;
  const w = Number($("logoSize").value) * cw;
  const h = w * logoAspect;
  const m = 0.035 * Math.max(cw, ch);
  const corner = $("logoPosition").value;
  const x = corner[1] === "l" ? m + w / 2 : cw - m - w / 2;
  const y = corner[0] === "t" ? m + h / 2 : ch - m - h / 2;
  return [x / cw, y / ch, w / cw];
}

function elementList() {
  const list = [];
  const d = draft();
  if (d.show_title && (d.frame_text || config.event_name)) list.push({ id: "title", entry: ed.pos.title });
  if (d.show_date) list.push({ id: "date", entry: ed.pos.date });
  if (hasLogo && d.logo.enabled) list.push({ id: "logo", entry: ed.pos.logo || defaultLogoPos() });
  (ed.pos.stickers || []).forEach((s, i) => list.push({ id: `sticker-${i}`, entry: s.slice(1), kind: s[0] }));
  return list;
}

function renderElements() {
  const stage = $("edStage");
  if (!ed.pos || !ed.style) return;
  stage.querySelectorAll(".ed-el").forEach((el) => el.remove());
  const [W, H] = stageSize();
  if (!W) return;
  const d = draft();
  const date = new Date().toLocaleDateString("de-CH", { day: "2-digit", month: "2-digit", year: "numeric" });
  for (const item of elementList()) {
    if (!item.entry) continue;
    const [x, y, s] = item.entry;
    const el = document.createElement("div");
    el.className = "ed-el";
    el.dataset.id = item.id;
    el.style.left = `${x * 100}%`;
    el.style.top = `${y * 100}%`;
    if (item.id === "title") {
      const style = ed.style.font;
      el.textContent = style === "elegant" ? (d.frame_text || config.event_name).toUpperCase() : (d.frame_text || config.event_name);
      el.style.fontFamily = style === "script" ? '"Great Vibes"' : "Outfit";
      el.style.fontWeight = style === "elegant" ? 300 : style === "script" ? 400 : 800;
      el.style.letterSpacing = style === "elegant" ? "0.18em" : "0";
      el.style.fontSize = `${s * H}px`;
      el.style.color = ed.style.title_color;
    } else if (item.id === "date") {
      el.textContent = date;
      el.style.fontFamily = "Outfit";
      el.style.fontWeight = 500;
      el.style.letterSpacing = "0.3em";
      el.style.fontSize = `${s * H}px`;
      el.style.color = ed.style.subtitle_color;
    } else if (item.id === "logo") {
      el.innerHTML = `<img alt="" src="/uploads/logo.png?t=${Date.now()}">`;
      el.style.width = `${s * W}px`;
    } else {
      el.innerHTML = `<img alt="" src="/api/stickers/${item.kind}.png">`;
      el.style.width = `${(s * H) / 0.75}px`;  // Sticker-Bild hat Rand um das Motiv
    }
    if (ed.selected === item.id) el.classList.add("selected");
    el.addEventListener("pointerdown", (e) => startDrag(e, el, item));
    stage.appendChild(el);
  }
}

function entryRef(id) {
  if (id === "title" || id === "date") return ed.pos[id];
  if (id === "logo") return (ed.pos.logo = ed.pos.logo || defaultLogoPos());
  return ed.pos.stickers[Number(id.split("-")[1])];
}

function startDrag(e, el, item) {
  e.preventDefault();
  select(item.id);
  el.setPointerCapture(e.pointerId);
  const ref = entryRef(item.id);
  const off = item.id.startsWith("sticker") ? 1 : 0;  // Sticker: [art, x, y, grösse]
  const move = (ev) => {
    const r = $("edBg").getBoundingClientRect();
    ref[off] = Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width));
    ref[off + 1] = Math.min(1, Math.max(0, (ev.clientY - r.top) / r.height));
    el.style.left = `${ref[off] * 100}%`;
    el.style.top = `${ref[off + 1] * 100}%`;
  };
  const up = () => {
    el.removeEventListener("pointermove", move);
    el.removeEventListener("pointerup", up);
    savePositions();
    scheduleEditor();
  };
  el.addEventListener("pointermove", move);
  el.addEventListener("pointerup", up);
}

function select(id) {
  ed.selected = id;
  document.querySelectorAll(".ed-el").forEach((el) => el.classList.toggle("selected", el.dataset.id === id));
  const slider = $("edSize");
  const ref = entryRef(id);
  const sticker = id.startsWith("sticker");
  const names = { title: "Titel", date: "Datum", logo: "Logo" };
  $("edSelName").textContent = `Grösse: ${names[id] || "Sticker"}`;
  [slider.min, slider.max] = id === "logo" ? [0.04, 0.6] : sticker ? [0.03, 0.45] : [0.01, 0.2];
  slider.value = ref[sticker ? 3 : 2];
  slider.disabled = false;
  $("edRemove").disabled = !sticker;
}

function resize() {
  if (!ed.selected) return;
  const ref = entryRef(ed.selected);
  ref[ed.selected.startsWith("sticker") ? 3 : 2] = Number($("edSize").value);
  savePositions();
  renderElements();
  scheduleEditor();
}

function addSticker(kind) {
  ed.pos.stickers = ed.pos.stickers || [];
  ed.pos.stickers.push([kind, 0.5, 0.5, 0.12]);
  savePositions();
  renderElements();
  select(`sticker-${ed.pos.stickers.length - 1}`);
  scheduleEditor();
}

function removeSticker() {
  if (!ed.selected || !ed.selected.startsWith("sticker")) return;
  ed.pos.stickers.splice(Number(ed.selected.split("-")[1]), 1);
  ed.selected = null;
  $("edSize").disabled = true;
  $("edRemove").disabled = true;
  savePositions();
  renderElements();
  scheduleEditor();
}

// ------------------------------------------------------------------ Editor laden/aktualisieren
async function loadEditor() {
  ed.layout = $("edLayout").value || "single";
  const info = await api("/api/editor/info", { ...draft(), layout: ed.layout });
  ed.key = info.key;
  ed.custom = info.custom;
  ed.cell = info.cell;
  ed.pos = JSON.parse(JSON.stringify(info.positions));
  ed.selected = null;
  $("edSize").disabled = true;
  $("edRemove").disabled = true;
  $("edSelName").textContent = "Kein Element ausgewählt";
  document.querySelectorAll("#edStyle [data-builtin]").forEach((el) => (el.hidden = info.custom));
  const frame = frames.find((f) => f.id === $("frameInput").value);
  $("edTarget").textContent = info.custom
    ? "Eigener Rahmen: Titel, Datum, Logo und Sticker platzieren, Schrift und Farben der Texte wählen."
    : `Änderungen gelten für den Rahmen «${frame ? frame.label : ""}» im gewählten Layout.`;
  $("edStage").classList.toggle("portrait", info.cell[1] > info.cell[0]);
  fillStyle(info.style);
  await refreshEditor(true);
}

async function refreshEditor(background) {
  const body = { ...draft(), layout: ed.layout };
  if (background) await postImage($("edBg"), { ...body, background: true, w: 900 });
  renderElements();
  postImage($("edPreview"), { ...body, w: 700 });
}

function scheduleEditor(background = false) {
  clearTimeout(edTimer);
  edTimer = setTimeout(() => refreshEditor(background), 300);
}

// ------------------------------------------------------------------ Start (aus settings.js init)
async function initEditor(settings) {
  hasLogo = settings.logo;
  stickerNames = settings.stickers;
  refreshLogo();
  renderCustomList();
  fillLayoutSelect();

  const bar = $("edStickers");
  for (const [kind, label] of stickerNames) {
    const b = document.createElement("button");
    b.type = "button";
    b.title = label;
    b.innerHTML = `<img alt="${label}" src="/api/stickers/${kind}.png">`;
    b.onclick = () => addSticker(kind);
    bar.appendChild(b);
  }

  $("logoFile").onchange = uploadLogo;
  $("logoDelete").onclick = deleteLogo;
  $("customUpload").onclick = uploadCustom;
  $("edLayout").onchange = loadEditor;
  $("edSize").oninput = resize;
  $("edRemove").onclick = removeSticker;
  $("edResetPos").onclick = () => {
    const edits = editsFor(ed.key);
    if (edits.pos) delete edits.pos[ed.layout];
    loadEditor();
  };
  $("edResetAll").onclick = () => {
    if (!confirm("Alle Änderungen an diesem Rahmen zurücksetzen?")) return;
    delete config.design.edits[ed.key];
    loadEditor();
  };
  document.querySelectorAll("#edStyle [data-style]").forEach((el) => el.addEventListener("input", readStyle));
  for (const id of ["logoEnabled", "logoPosition", "logoSize", "titleInput", "showTitle", "showDate"]) {
    $(id).addEventListener("input", () => scheduleEditor());
  }
  addEventListener("resize", renderElements);

  // Auswahl in der Rahmen-Galerie wechselt auch den Editor
  const choose = selectFrame;
  selectFrame = (id) => {
    choose(id);
    if (ed.key !== null) loadEditor();
  };
  await loadEditor();
}
