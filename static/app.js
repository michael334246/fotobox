// Fotobox – Bedienoberfläche
const $ = (id) => document.getElementById(id);

const PHRASES = [
  "Cheese! 🧀", "Party-Face! 🥳", "Alle zusammen! 🙌", "Grimasse! 🤪", "Küsschen! 😘",
  "Rockstar! 🤘", "Ganz cool! 😎", "Lachen! 😂", "Überrascht! 😲", "Herzchen! 💖",
];
const NEXT_POSE = ["Nächste Pose! 🤪", "Jetzt was Verrücktes! 🙃", "Und nochmal! 😁", "Andere Pose! 💃"];

let state = null;
let layout = null;         // gewähltes Layout {id, label, shots}
let frame = null;          // gewählter Rahmen (nur wenn Gäste wählen dürfen)
let frames = [];
let current = null;        // aktuell angezeigtes Foto {name, url}
let busy = false;
let copies = 1;
let reviewTimer = null;
let liveTimer = null;
let liveSource = null;     // <video> oder <img>, aus dem die Vorschau gezeichnet wird
let view = null;           // Rahmen der Live-Vorschau {size, holes, overlayImg}
let taken = [];            // bereits aufgenommene Bilder dieser Serie (Image)

const pick = (list) => list[Math.floor(Math.random() * list.length)];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(url, options = {}) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) throw new Error(data.error || `Fehler ${res.status}`);
  return data;
}

function toast(text, ms = 3500) {
  const t = $("toast");
  t.textContent = text;
  t.hidden = false;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => (t.hidden = true), ms);
}

function show(screen) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.toggle("active", s.id === screen));
  clearTimeout(reviewTimer);
  if (screen === "liveScreen") $("shareModal").hidden = true;
  if (screen !== "liveScreen") $("frameModal").hidden = true;
  if (screen !== "liveScreen") $("filterModal").hidden = true;
  if (screen !== "liveScreen" && state.review_timeout > 0) {
    reviewTimer = setTimeout(() => show("liveScreen"), state.review_timeout * 1000);
  }
}

// ------------------------------------------------------------------ Konfetti
function confetti() {
  const canvas = $("confetti");
  const ctx = canvas.getContext("2d");
  canvas.width = innerWidth;
  canvas.height = innerHeight;
  const colors = ["#38bdf8", "#67e8f9", "#3b82f6", "#ffffff", "#a5b4fc", "#fcd34d"];
  const parts = Array.from({ length: 160 }, () => ({
    x: canvas.width / 2 + (Math.random() - 0.5) * canvas.width * 0.3,
    y: canvas.height * 0.55,
    vx: (Math.random() - 0.5) * 22,
    vy: -Math.random() * 22 - 8,
    size: 6 + Math.random() * 8,
    rot: Math.random() * Math.PI,
    vr: (Math.random() - 0.5) * 0.4,
    color: pick(colors),
  }));
  const start = performance.now();
  (function step(now) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const p of parts) {
      p.vy += 0.55;
      p.vx *= 0.99;
      p.x += p.vx;
      p.y += p.vy;
      p.rot += p.vr;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rot);
      ctx.fillStyle = p.color;
      ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2);
      ctx.restore();
    }
    if (now - start < 3500) requestAnimationFrame(step);
    else ctx.clearRect(0, 0, canvas.width, canvas.height);
  })(start);
}

// ------------------------------------------------------------------ Kamera
async function startWebcam() {
  const video = $("video");
  liveSource = video;
  const constraints = {
    audio: false,
    video: {
      width: { ideal: 4096 },
      height: { ideal: 2160 },
      ...(state.camera.webcam_device_id ? { deviceId: { exact: state.camera.webcam_device_id } } : {}),
    },
  };
  try {
    video.srcObject = await navigator.mediaDevices.getUserMedia(constraints);
  } catch (err) {
    cameraMessage(`Kamera nicht verfügbar: ${err.message}`);
  }
}

function startDslrPreview() {
  // Einzelbilder abwechselnd laden, damit immer ein vollständiges Bild gezeichnet wird
  const base = state.camera.digicam_url.replace(/\/$/, "");
  api("/api/liveview/start", { method: "POST" }).catch((e) => cameraMessage(e.message));
  const next = () => {
    const img = new Image();
    img.onload = () => {
      liveSource = img;
      liveTimer = setTimeout(next, 80);
    };
    img.onerror = () => (liveTimer = setTimeout(next, 500));
    img.src = `${base}/liveview.jpg?t=${Date.now()}`;
  };
  next();
}

function startGphotoPreview() {
  // MJPEG-Stream vom Server; wird beim Auslösen beendet und danach neu gestartet
  const img = $("dslrView");
  liveSource = img;
  img.onerror = () => {
    cameraMessage("Keine Live-Ansicht – ist die Kamera angeschlossen und eingeschaltet?");
    clearTimeout(liveTimer);
    liveTimer = setTimeout(startGphotoPreview, 3000);
  };
  img.onload = () => cameraMessage("");
  img.src = `/api/liveview.mjpg?t=${Date.now()}`;
}

function stopGphotoPreview() {
  clearTimeout(liveTimer);
  $("dslrView").onerror = null;
  $("dslrView").src = "";
}

function cameraMessage(text) {
  const m = $("cameraMessage");
  m.textContent = text;
  m.hidden = !text;
}

async function captureShot() {
  if (state.camera.mode === "webcam") {
    const video = $("video");
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    return uploadShot(applyFilters(canvas));
  }
  if (state.camera.mode === "gphoto2") stopGphotoPreview();
  let shot;
  try {
    shot = (await api("/api/capture", { method: "POST" })).shot;
  } finally {
    if (state.camera.mode === "gphoto2") startGphotoPreview();
  }
  if (!filtersActive()) return shot;
  // Spiegelreflex: Filter nachträglich auf das Kamerafoto anwenden
  const img = await loadImage(`/shots/${shot}`);
  const canvas = document.createElement("canvas");
  [canvas.width, canvas.height] = [img.naturalWidth, img.naturalHeight];
  canvas.getContext("2d").drawImage(img, 0, 0);
  return uploadShot(applyFilters(canvas));
}

async function uploadShot(canvas) {
  const blob = await new Promise((r) => canvas.toBlob(r, "image/jpeg", 0.92));
  const form = new FormData();
  form.append("photo", blob, "photo.jpg");
  return (await api("/api/shot", { method: "POST", body: form })).shot;
}

// ------------------------------------------------------------------ Live-Vorschau mit Rahmen
function frameQuery() {
  return frame ? `?frame=${encodeURIComponent(frame)}` : "";
}

async function loadView() {
  const info = await api(`/api/layouts/${layout.id}/overlay${frameQuery()}`);
  let overlayImg = null;
  if (info.overlay) {
    overlayImg = new Image();
    overlayImg.src = `/api/layouts/${layout.id}/overlay.png${frameQuery()}`;
    await overlayImg.decode().catch(() => {});
  }
  view = { ...info, overlayImg, plain: !info.overlay };
}

function sourceSize(src) {
  if (src instanceof HTMLVideoElement) return [src.videoWidth, src.videoHeight];
  if (src instanceof HTMLCanvasElement) return [src.width, src.height];
  return [src.naturalWidth, src.naturalHeight];
}

function drawCover(ctx, src, x, y, w, h, radius, mirror) {
  const [sw, sh] = sourceSize(src);
  if (!sw || !sh) return;
  const scale = Math.max(w / sw, h / sh);
  const cw = w / scale, ch = h / scale;
  ctx.save();
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, radius);
  ctx.clip();
  if (mirror) {
    ctx.translate(x + w, y);
    ctx.scale(-1, 1);
    ctx.drawImage(src, (sw - cw) / 2, (sh - ch) / 2, cw, ch, 0, 0, w, h);
  } else {
    ctx.drawImage(src, (sw - cw) / 2, (sh - ch) / 2, cw, ch, x, y, w, h);
  }
  ctx.restore();
}

function renderPreview() {
  requestAnimationFrame(renderPreview);
  const canvas = $("preview");
  if (!view || !liveSource) return;
  const ctx = canvas.getContext("2d");
  const mirror = state.camera.mirror_preview;
  const live = filteredPreview(liveSource, ...sourceSize(liveSource));

  if (view.plain) {  // ohne Rahmen und ohne Text: Kamerabild im Originalformat
    const [sw, sh] = sourceSize(liveSource);
    if (!sw) return;
    if (canvas.width !== sw || canvas.height !== sh) [canvas.width, canvas.height] = [sw, sh];
    drawCover(ctx, live, 0, 0, sw, sh, 0, mirror);
    return;
  }

  const k = 0.6;
  const [W, H] = view.size.map((v) => Math.round(v * k));
  if (canvas.width !== W || canvas.height !== H) [canvas.width, canvas.height] = [W, H];
  ctx.fillStyle = "#0b1a3d";
  ctx.fillRect(0, 0, W, H);
  view.holes.forEach(([x1, y1, x2, y2, r], i) => {
    const n = i % layout.shots;
    const box = [x1 * k, y1 * k, (x2 - x1) * k, (y2 - y1) * k, r * k];
    if (taken[n]) drawCover(ctx, taken[n], ...box, false);
    else if (n === taken.length) drawCover(ctx, live, ...box, mirror);
    else {  // noch offenes Feld: Nummer anzeigen
      ctx.fillStyle = "#16284f";
      ctx.beginPath();
      ctx.roundRect(...box);
      ctx.fill();
      ctx.fillStyle = "rgba(255,255,255,0.35)";
      ctx.font = `700 ${Math.round(box[3] * 0.3)}px Outfit, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(String(n + 1), box[0] + box[2] / 2, box[1] + box[3] / 2);
    }
  });
  if (view.overlayImg) ctx.drawImage(view.overlayImg, 0, 0, W, H);
}

// ------------------------------------------------------------------ Layout-Auswahl
function previewUrl(layoutId, width) {
  const q = new URLSearchParams({ w: width });
  if (frame) q.set("frame", frame);
  return `/api/layouts/${layoutId}/preview.jpg?${q}`;
}

function renderLayoutPicker() {
  const box = $("layoutPicker");
  box.innerHTML = "";
  box.hidden = state.layouts.length < 2;
  for (const l of state.layouts) {
    const card = document.createElement("button");
    card.className = "layout-card";
    card.innerHTML = `<img alt=""><span></span><small></small>`;
    card.querySelector("img").src = previewUrl(l.id, 240);
    card.querySelector("span").textContent = l.label;
    card.querySelector("small").textContent = l.shots === 1 ? "1 Foto" : `${l.shots} Fotos`;
    card.onclick = () => selectLayout(l);
    card.dataset.id = l.id;
    box.appendChild(card);
  }
  selectLayout(layout && state.layouts.find((l) => l.id === layout.id)
    || state.layouts.find((l) => l.id === state.default_layout) || state.layouts[0]);
}

function selectLayout(l) {
  layout = l;
  document.querySelectorAll(".layout-card").forEach((c) => c.classList.toggle("selected", c.dataset.id === l.id));
  loadView().catch((e) => toast(e.message));
}

// ------------------------------------------------------------------ Rahmen-Auswahl (Gäste)
async function setupFramePicker() {
  if (!state.guest_frames) return;
  frames = await api("/api/frames");
  frame = state.frame;
  $("frameBtn").hidden = false;
  const grid = $("frameGrid");
  grid.innerHTML = "";
  for (const f of frames) {
    const card = document.createElement("button");
    card.className = "frame-card";
    card.dataset.id = f.id;
    card.innerHTML = `<img alt="" loading="lazy"><span></span>`;
    card.querySelector("img").src = `/api/layouts/single/preview.jpg?frame=${f.id}&w=320`;
    card.querySelector("span").textContent = f.label;
    card.onclick = () => {
      selectFrame(f.id);
      $("frameModal").hidden = true;
    };
    grid.appendChild(card);
  }
  selectFrame(frame);
  $("frameBtn").onclick = () => ($("frameModal").hidden = false);
  $("frameClose").onclick = () => ($("frameModal").hidden = true);
}

function selectFrame(id) {
  frame = id;
  const f = frames.find((x) => x.id === id);
  $("frameName").textContent = f ? f.label : "";
  document.querySelectorAll(".frame-card").forEach((c) => c.classList.toggle("selected", c.dataset.id === id));
  renderLayoutPicker();
}

// ------------------------------------------------------------------ Beenden (nur mit Passwort)
function setupExit() {
  const input = $("exitPassword");
  const keypad = $("keypad");
  for (const key of ["1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫", "0", "✓"]) {
    const b = document.createElement("button");
    b.textContent = key;
    b.onclick = () => {
      if (key === "⌫") input.value = input.value.slice(0, -1);
      else if (key === "✓") confirmExit();
      else input.value += key;
    };
    keypad.appendChild(b);
  }
  $("exitBtn").onclick = () => {
    input.value = "";
    $("exitError").textContent = "";
    $("exitModal").hidden = false;
    input.focus();
  };
  $("exitCancel").onclick = () => ($("exitModal").hidden = true);
  $("exitConfirm").onclick = confirmExit;
  input.addEventListener("keydown", (e) => {
    e.stopPropagation(); // Leertaste/Enter sollen hier kein Foto auslösen
    if (e.key === "Enter") confirmExit();
  });
}

async function confirmExit() {
  try {
    await api("/api/exit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: $("exitPassword").value }),
    });
    $("exitModal").hidden = true;
    toast("Fotobox wird beendet …", 10000);
  } catch (err) {
    $("exitError").textContent = err.message;
    $("exitPassword").value = "";
  }
}

// ------------------------------------------------------------------ Ablauf
async function countdown(seconds) {
  const cd = $("countdown");
  const num = $("countNum");
  const phrase = $("countPhrase");
  cd.hidden = false;
  phrase.textContent = "";
  for (let i = seconds; i > 0; i--) {
    num.textContent = i;
    num.classList.remove("pop");
    void num.offsetWidth; // Animation neu starten
    num.classList.add("pop");
    if (i === 1) phrase.textContent = pick(PHRASES);
    await sleep(1000);
  }
  num.textContent = "";
}

function flash() {
  const f = $("flash");
  f.classList.add("on");
  setTimeout(() => f.classList.remove("on"), 60);
}

function loadImage(url) {
  const img = new Image();
  img.src = url;
  return img.decode().then(() => img);
}

async function takePhoto() {
  if (busy || !$("liveScreen").classList.contains("active")) return;
  busy = true;
  document.body.classList.add("shooting");
  const badge = $("shotBadge");
  const cd = $("countdown");
  taken = [];
  const shots = [];
  try {
    for (let n = 1; n <= layout.shots; n++) {
      if (layout.shots > 1) {
        badge.textContent = `Foto ${n} von ${layout.shots}`;
        badge.hidden = false;
      }
      if (n > 1) {
        cd.hidden = false;
        $("countNum").textContent = "";
        $("countPhrase").textContent = pick(NEXT_POSE);
        await sleep(1300);
      }
      await countdown(state.countdown);
      $("countPhrase").textContent = "";
      flash();
      const shot = await captureShot();
      shots.push(shot);
      if (n < layout.shots) taken.push(await loadImage(`/shots/${shot}`));
    }
    cd.hidden = true;
    badge.hidden = true;
    $("busyOverlay").hidden = false;
    const photo = await api("/api/compose", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ layout: layout.id, shots, frame }),
    });
    await loadImage(photo.url).catch(() => {});
    $("busyOverlay").hidden = true;
    openReview(photo);
    confetti();
  } catch (err) {
    toast(err.message, 6000);
  } finally {
    cd.hidden = true;
    badge.hidden = true;
    $("busyOverlay").hidden = true;
    taken = [];
    document.body.classList.remove("shooting");
    busy = false;
  }
}

function openReview(photo) {
  current = photo;
  copies = 1;
  $("copies").textContent = copies;
  const img = $("reviewImg");
  img.style.animation = "none";
  void img.offsetWidth;
  img.style.animation = "";
  img.src = photo.url;
  show("reviewScreen");
}

async function printPhoto() {
  const btn = $("printBtn");
  btn.disabled = true;
  try {
    const r = await api(`/api/photos/${current.name}/print`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ copies }),
    });
    toast(r.copies > 1 ? `${r.copies} Ausdrucke kommen gleich!` : "Dein Foto wird gedruckt!");
  } catch (err) {
    toast(err.message, 6000);
  } finally {
    setTimeout(() => (btn.disabled = false), 3000);
  }
}

async function sharePhoto() {
  const btn = $("shareBtn");
  btn.disabled = true;
  toast("Foto wird hochgeladen …", 20000);
  try {
    const r = await api(`/api/photos/${current.name}/share`, { method: "POST" });
    $("toast").hidden = true;
    $("shareQr").src = r.qr;
    $("shareLink").textContent = r.link;
    $("shareModal").hidden = false;
    show("reviewScreen"); // Timer neu starten
  } catch (err) {
    toast(err.message, 6000);
  } finally {
    btn.disabled = false;
  }
}

async function openGallery() {
  const g = $("gallery");
  g.innerHTML = "";
  const photos = await api("/api/photos");
  for (const p of photos) {
    const img = document.createElement("img");
    img.src = p.url;
    img.loading = "lazy";
    img.onclick = () => openReview(p);
    g.appendChild(img);
  }
  if (!photos.length) g.textContent = "Noch keine Fotos – los geht's! 📸";
  show("galleryScreen");
}

// ------------------------------------------------------------------ Start
async function init() {
  state = await api("/api/state");
  document.title = state.event_name;
  $("printGroup").hidden = !state.print_enabled;
  $("shareBtn").hidden = !state.share_enabled;
  renderLayoutPicker();
  await setupFramePicker().catch(() => {});
  setupFilters(state.filters_enabled);
  setupExit();

  if (state.camera.mode === "dslr") startDslrPreview();
  else if (state.camera.mode === "gphoto2") startGphotoPreview();
  else startWebcam();
  renderPreview();

  $("shutterBtn").onclick = takePhoto;
  $("againBtn").onclick = () => show("liveScreen");
  $("printBtn").onclick = printPhoto;
  $("shareBtn").onclick = sharePhoto;
  $("shareClose").onclick = () => ($("shareModal").hidden = true);
  $("galleryBtn").onclick = openGallery;
  $("galleryClose").onclick = () => show("liveScreen");
  $("copiesMinus").onclick = () => ($("copies").textContent = copies = Math.max(1, copies - 1));
  $("copiesPlus").onclick = () => ($("copies").textContent = copies = Math.min(state.max_copies, copies + 1));

  document.addEventListener("keydown", (e) => {
    if (!$("exitModal").hidden) return;
    if (e.code === "Space" || e.code === "Enter") {
      e.preventDefault();
      if (!$("frameModal").hidden) $("frameModal").hidden = true;
      else if (!$("filterModal").hidden) $("filterModal").hidden = true;
      else if ($("liveScreen").classList.contains("active")) takePhoto();
      else if (!$("shareModal").hidden) $("shareModal").hidden = true;
      else show("liveScreen");
    }
    // Pfeiltasten wechseln das Layout (praktisch mit Buzzer/Fernbedienung)
    if ((e.code === "ArrowLeft" || e.code === "ArrowRight") && !busy && state.layouts.length > 1) {
      const i = state.layouts.indexOf(layout);
      const next = (i + (e.code === "ArrowRight" ? 1 : -1) + state.layouts.length) % state.layouts.length;
      selectLayout(state.layouts[next]);
    }
  });
  // Jede Berührung setzt den Rückkehr-Timer zurück
  document.addEventListener("pointerdown", () => {
    const active = document.querySelector(".screen.active");
    if (active && active.id !== "liveScreen") show(active.id);
  });
}

init().catch((err) => toast(err.message, 10000));
