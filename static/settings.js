// Fotobox – Einstellungsseite
const $ = (id) => document.getElementById(id);
let config = null;
let types = {};
let frames = [];       // [{id, label, title}, …]
let layoutNames = [];

async function api(url, body) {
  const options = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
  const res = await fetch(url, options);
  if (res.status === 401) location.href = "/login";
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) throw new Error(data.error || `Fehler ${res.status}`);
  return data;
}

function status(el, text, ok = true) {
  el.textContent = text;
  el.className = ok ? "status-ok" : "status-err";
}

const getPath = (obj, path) => path.split(".").reduce((o, k) => o?.[k], obj);
function setPath(obj, path, value) {
  const keys = path.split(".");
  const last = keys.pop();
  keys.reduce((o, k) => (o[k] ??= {}), obj)[last] = value;
}

function readInput(el) {
  if (el.type === "checkbox") return el.checked;
  if (el.type === "number" || el.type === "range") return Number(el.value);
  return el.value;
}
function writeInput(el, value) {
  if (el.type === "checkbox") el.checked = !!value;
  else el.value = value ?? "";
}

function setOptions(select, options, selected) {
  select.innerHTML = "";
  for (const [value, label] of options) {
    const o = document.createElement("option");
    o.value = value;
    o.textContent = label;
    select.appendChild(o);
  }
  if (selected && !options.some(([v]) => v === selected)) {
    const o = document.createElement("option");
    o.value = selected;
    o.textContent = `${selected} (nicht gefunden)`;
    select.appendChild(o);
  }
  select.value = selected ?? "";
}

// ------------------------------------------------------------------ Rahmen & Titel
let previewTimer = null;

function previewParams() {
  const q = new URLSearchParams({
    title: $("titleInput").value,
    show_title: $("showTitle").checked ? "1" : "0",
    show_date: $("showDate").checked ? "1" : "0",
  });
  return q;
}

function renderDesign() {
  setOptions($("defaultLayout"), layoutNames, config.design.default_layout);
  const box = $("layoutChecks");
  box.innerHTML = "";
  for (const [id, label] of layoutNames) {
    const l = document.createElement("label");
    l.className = "check";
    l.innerHTML = `<input type="checkbox" value="${id}"> <span></span>`;
    l.querySelector("span").textContent = label;
    l.querySelector("input").checked = config.design.layouts.includes(id);
    box.appendChild(l);
  }

  const gallery = $("frameGallery");
  gallery.innerHTML = "";
  for (const f of frames) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "frame-card";
    card.dataset.id = f.id;
    card.innerHTML = `<img alt="" loading="lazy"><span></span>`;
    card.querySelector("span").textContent = f.label;
    card.onclick = () => selectFrame(f.id);
    gallery.appendChild(card);
  }
  $("titleInput").placeholder = `leer = ${config.event_name}`;
  $("titleSuggest").onclick = () => {
    const f = frames.find((x) => x.id === $("frameInput").value);
    if (f && f.title) {
      $("titleInput").value = f.title;
      $("showTitle").checked = true;
      updateDesignUi();
    }
  };
  for (const id of ["titleInput", "showTitle", "showDate"]) $(id).addEventListener("input", updateDesignUi);
  selectFrame(config.design.frame);
}

function selectFrame(id) {
  $("frameInput").value = id;
  document.querySelectorAll(".frame-card").forEach((c) => c.classList.toggle("selected", c.dataset.id === id));
  updateDesignUi();
}

function updateDesignUi() {
  const f = frames.find((x) => x.id === $("frameInput").value);
  const btn = $("titleSuggest");
  btn.hidden = !(f && f.title);
  if (f && f.title) btn.textContent = `Vorschlag: «${f.title}»`;
  $("titleRow").style.opacity = $("showTitle").checked ? "1" : "0.45";
  clearTimeout(previewTimer);
  previewTimer = setTimeout(refreshPreviews, 350);
}

function refreshPreviews() {
  const q = previewParams();
  document.querySelectorAll(".frame-card").forEach((card) => {
    const p = new URLSearchParams(q);
    p.set("frame", card.dataset.id);
    p.set("w", "320");
    card.querySelector("img").src = `/api/layouts/single/preview.jpg?${p}`;
  });
  const box = $("layoutPreviews");
  box.innerHTML = "";
  for (const [id, label] of layoutNames) {
    const p = new URLSearchParams(q);
    p.set("frame", $("frameInput").value);
    p.set("w", "520");
    const fig = document.createElement("figure");
    fig.innerHTML = `<img alt=""><figcaption></figcaption>`;
    fig.querySelector("img").src = `/api/layouts/${id}/preview.jpg?${p}`;
    fig.querySelector("figcaption").textContent = label;
    box.appendChild(fig);
  }
}

// ------------------------------------------------------------------ Kamera
function updateCameraMode() {
  const mode = $("cameraMode").value;
  $("webcamOptions").hidden = mode !== "webcam";
  $("dslrOptions").hidden = mode !== "dslr";
  $("gphotoOptions").hidden = mode !== "gphoto2";
}

async function loadWebcams() {
  try {
    // Kurz Zugriff anfragen, damit der Browser die Gerätenamen verrät
    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
    stream.getTracks().forEach((t) => t.stop());
  } catch (_) { /* ohne Berechtigung gibt es nur anonyme Einträge */ }
  const devices = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "videoinput");
  setOptions(
    $("webcamSelect"),
    [["", "Standardkamera"], ...devices.map((d, i) => [d.deviceId, d.label || `Kamera ${i + 1}`])],
    config.camera.webcam_device_id,
  );
}

// ------------------------------------------------------------------ Drucker
async function loadPrinters() {
  const r = await api("/api/printers");
  setOptions(
    $("printerSelect"),
    [["", `Standarddrucker${r.default ? ` (${r.default})` : ""}`], ...r.printers.map((p) => [p, p])],
    $("printerSelect").value || config.printer.name,
  );
}

// ------------------------------------------------------------------ Cloudspeicher
function renderStorages() {
  const box = $("storages");
  box.innerHTML = "";
  config.cloud.storages.forEach((s, index) => {
    const node = $("storageTpl").content.firstElementChild.cloneNode(true);
    const type = types[s.type];
    node.querySelector(".storage-type").textContent = type ? type.label : s.type;

    const fields = node.querySelector(".fields");
    for (const f of type?.fields || []) {
      const label = document.createElement("label");
      label.innerHTML = `<span></span><input data-field="${f.key}" type="${f.type}">`;
      label.querySelector("span").textContent = f.label;
      if (f.placeholder) label.querySelector("input").placeholder = f.placeholder;
      fields.appendChild(label);
    }
    node.querySelectorAll("[data-field]").forEach((el) => {
      writeInput(el, s[el.dataset.field]);
      el.addEventListener("input", () => {
        s[el.dataset.field] = readInput(el);
        if (el.dataset.field === "name") renderShareSelect();
      });
    });

    const st = node.querySelector(".status");
    node.querySelector(".remove").onclick = () => {
      if (!confirm(`Cloudspeicher «${s.name}» entfernen?`)) return;
      config.cloud.storages.splice(index, 1);
      renderStorages();
    };
    node.querySelector(".test").onclick = async () => {
      status(st, "Teste …");
      try {
        await api("/api/storages/test", s);
        status(st, "✔ Verbindung erfolgreich");
      } catch (e) {
        status(st, `✖ ${e.message}`, false);
      }
    };

    if (s.type === "dropbox") {
      node.querySelector(".dropbox-connect").hidden = false;
      node.querySelector(".dbx-open").onclick = async () => {
        if (!s.app_key) return status(st, "Zuerst App key eintragen.", false);
        const r = await api("/api/dropbox/auth-url", { app_key: s.app_key });
        window.open(r.url, "_blank");
      };
      node.querySelector(".dbx-exchange").onclick = async () => {
        try {
          const r = await api("/api/dropbox/exchange", {
            app_key: s.app_key, app_secret: s.app_secret, code: node.querySelector(".dbx-code").value,
          });
          s.refresh_token = r.refresh_token;
          node.querySelector('[data-field="refresh_token"]').value = r.refresh_token;
          status(st, "✔ Dropbox verbunden – bitte speichern");
        } catch (e) {
          status(st, `✖ ${e.message}`, false);
        }
      };
    }
    box.appendChild(node);
  });
  renderShareSelect();
}

function renderShareSelect() {
  setOptions(
    $("shareStorage"),
    [["", "— Teilen deaktiviert —"], ...config.cloud.storages.map((s) => [s.id, s.name || types[s.type]?.label])],
    config.cloud.share_storage_id,
  );
}

function addStorage() {
  const type = $("newStorageType").value;
  const storage = { id: Math.random().toString(16).slice(2, 10), type, name: types[type].label, auto_upload: true };
  for (const f of types[type].fields) storage[f.key] = "";
  config.cloud.storages.push(storage);
  if (!config.cloud.share_storage_id && type !== "folder") config.cloud.share_storage_id = storage.id;
  renderStorages();
}

// ------------------------------------------------------------------ Speichern
async function save() {
  document.querySelectorAll("[data-key]").forEach((el) => setPath(config, el.dataset.key, readInput(el)));
  config.design.layouts = [...document.querySelectorAll("#layoutChecks input:checked")].map((i) => i.value);
  if (!config.design.layouts.length) config.design.layouts = ["classic"];
  if (!config.design.layouts.includes(config.design.default_layout)) {
    config.design.default_layout = config.design.layouts[0];
  }
  try {
    const r = await api("/api/settings", config);
    config = r.config;
    $("defaultLayout").value = config.design.default_layout;
    status($("saveStatus"), "✔ Gespeichert");
  } catch (e) {
    status($("saveStatus"), `✖ ${e.message}`, false);
  }
}

async function init() {
  const r = await api("/api/settings");
  config = r.config;
  types = r.storage_types;
  frames = r.frames;
  layoutNames = r.layouts;

  setOptions($("newStorageType"), Object.entries(types).map(([k, t]) => [k, t.label]));
  await Promise.all([loadPrinters().catch(() => {}), loadWebcams().catch(() => {})]);
  document.querySelectorAll("[data-key]").forEach((el) => writeInput(el, getPath(config, el.dataset.key)));
  renderDesign();
  renderStorages();
  updateCameraMode();
  initEditor(r).catch((e) => console.error(e));

  $("cameraMode").onchange = updateCameraMode;
  $("webcamRefresh").onclick = loadWebcams;
  $("printerRefresh").onclick = loadPrinters;
  $("addStorage").onclick = addStorage;
  $("saveBtn").onclick = save;
  $("shareStorage").onchange = (e) => (config.cloud.share_storage_id = e.target.value);

  $("printerConnect").onclick = async () => {
    try {
      const res = await api("/api/printers/connect", { path: $("sharePath").value });
      await loadPrinters();
      if (res.name) $("printerSelect").value = res.name;
      status($("printerStatus"), `✔ ${res.message}`);
    } catch (e) {
      status($("printerStatus"), `✖ ${e.message}`, false);
    }
  };
  $("printerTest").onclick = async () => {
    await save();
    status($("printerStatus"), "Drucke …");
    try {
      await api("/api/printers/test", {});
      status($("printerStatus"), "✔ Testseite gesendet");
    } catch (e) {
      status($("printerStatus"), `✖ ${e.message}`, false);
    }
  };
}

init().catch((e) => alert(e.message));
