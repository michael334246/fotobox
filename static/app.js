// Fotobox – Bedienoberfläche
const $ = (id) => document.getElementById(id);

const PHRASES = [
  "Cheese! 🧀", "Party-Face! 🥳", "Alle zusammen! 🙌", "Grimasse! 🤪", "Küsschen! 😘",
  "Rockstar! 🤘", "Ganz cool! 😎", "Lachen! 😂", "Überrascht! 😲", "Herzchen! 💖",
];
const NEXT_POSE = ["Nächste Pose! 🤪", "Jetzt was Verrücktes! 🙃", "Und nochmal! 😁", "Andere Pose! 💃"];

let state = null;
let layout = null;         // gewähltes Layout {id, label, shots}
let current = null;        // aktuell angezeigtes Foto {name, url}
let busy = false;
let copies = 1;
let reviewTimer = null;
let liveTimer = null;

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
  const colors = ["#ffd166", "#f72585", "#4cc9f0", "#7209b7", "#ffffff", "#ff9e00", "#06d6a0"];
  const parts = Array.from({ length: 180 }, () => ({
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
  (function frame(now) {
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
    if (now - start < 3500) requestAnimationFrame(frame);
    else ctx.clearRect(0, 0, canvas.width, canvas.height);
  })(start);
}

// ------------------------------------------------------------------ Kamera
async function startWebcam() {
  const video = $("video");
  video.hidden = false;
  video.classList.toggle("mirror", state.camera.mirror_preview);
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
  const img = $("dslrView");
  img.hidden = false;
  img.classList.toggle("mirror", state.camera.mirror_preview);
  const base = state.camera.digicam_url.replace(/\/$/, "");
  api("/api/liveview/start", { method: "POST" }).catch((e) => cameraMessage(e.message));
  img.onerror = () => {};
  const refresh = () => {
    if (!busy) img.src = `${base}/liveview.jpg?t=${Date.now()}`;
    liveTimer = setTimeout(refresh, 100);
  };
  refresh();
}

function startGphotoPreview() {
  // MJPEG-Stream vom Server; wird beim Auslösen beendet und danach neu gestartet
  const img = $("dslrView");
  img.hidden = false;
  img.classList.toggle("mirror", state.camera.mirror_preview);
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
    const blob = await new Promise((r) => canvas.toBlob(r, "image/jpeg", 0.92));
    const form = new FormData();
    form.append("photo", blob, "photo.jpg");
    const r = await api("/api/shot", { method: "POST", body: form });
    return { shot: r.shot, thumb: URL.createObjectURL(blob) };
  }
  if (state.camera.mode === "gphoto2") stopGphotoPreview();
  try {
    const r = await api("/api/capture", { method: "POST" });
    return { shot: r.shot, thumb: null };
  } finally {
    if (state.camera.mode === "gphoto2") startGphotoPreview();
  }
}

// ------------------------------------------------------------------ Layout-Auswahl
function renderLayoutPicker() {
  const box = $("layoutPicker");
  box.innerHTML = "";
  box.hidden = state.layouts.length < 2;
  for (const l of state.layouts) {
    const card = document.createElement("button");
    card.className = "layout-card";
    card.innerHTML = `<img alt=""><span></span><small></small>`;
    card.querySelector("img").src = `/api/layouts/${l.id}/preview.jpg?v=${Date.now()}`;
    card.querySelector("span").textContent = l.label;
    card.querySelector("small").textContent = l.shots === 1 ? "1 Foto" : `${l.shots} Fotos`;
    card.onclick = () => selectLayout(l);
    card.dataset.id = l.id;
    box.appendChild(card);
  }
  selectLayout(state.layouts.find((l) => l.id === state.default_layout) || state.layouts[0]);
}

function selectLayout(l) {
  layout = l;
  document.querySelectorAll(".layout-card").forEach((c) => c.classList.toggle("selected", c.dataset.id === l.id));
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

async function takePhoto() {
  if (busy || !$("liveScreen").classList.contains("active")) return;
  busy = true;
  document.body.classList.add("shooting");
  const thumbs = $("shotThumbs");
  const badge = $("shotBadge");
  const cd = $("countdown");
  thumbs.innerHTML = "";
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
      shots.push(shot.shot);
      if (shot.thumb) {
        const img = document.createElement("img");
        img.src = shot.thumb;
        thumbs.appendChild(img);
      }
    }
    cd.hidden = true;
    badge.hidden = true;
    $("busyOverlay").hidden = false;
    const photo = await api("/api/compose", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ layout: layout.id, shots }),
    });
    await preload(photo.url);
    $("busyOverlay").hidden = true;
    openReview(photo);
    confetti();
  } catch (err) {
    toast(err.message, 6000);
  } finally {
    cd.hidden = true;
    badge.hidden = true;
    $("busyOverlay").hidden = true;
    thumbs.innerHTML = "";
    document.body.classList.remove("shooting");
    busy = false;
  }
}

function preload(url) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = img.onerror = resolve;
    img.src = url;
  });
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
    toast(r.copies > 1 ? `🖨️ ${r.copies} Ausdrucke kommen gleich!` : "🖨️ Dein Foto wird gedruckt!");
  } catch (err) {
    toast(err.message, 6000);
  } finally {
    setTimeout(() => (btn.disabled = false), 3000);
  }
}

async function sharePhoto() {
  const btn = $("shareBtn");
  btn.disabled = true;
  toast("☁️ Foto wird hochgeladen …", 20000);
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

  if (state.camera.mode === "dslr") startDslrPreview();
  else if (state.camera.mode === "gphoto2") startGphotoPreview();
  else startWebcam();

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
    if (e.code === "Space" || e.code === "Enter") {
      e.preventDefault();
      if ($("liveScreen").classList.contains("active")) takePhoto();
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
