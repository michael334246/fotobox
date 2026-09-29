// Fotobox – Bedienoberfläche
const $ = (id) => document.getElementById(id);

let state = null;
let current = null;       // aktuell angezeigtes Foto {name, url}
let busy = false;
let copies = 1;
let reviewTimer = null;
let liveTimer = null;

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

function cameraMessage(text) {
  const m = $("cameraMessage");
  m.textContent = text;
  m.hidden = !text;
}

async function grabWebcamFrame() {
  const video = $("video");
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  const blob = await new Promise((r) => canvas.toBlob(r, "image/jpeg", 0.92));
  const form = new FormData();
  form.append("photo", blob, "photo.jpg");
  return api("/api/photo", { method: "POST", body: form });
}

// ------------------------------------------------------------------ Ablauf
function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function takePhoto() {
  if (busy || !$("liveScreen").classList.contains("active")) return;
  busy = true;
  const cd = $("countdown");
  try {
    for (let i = state.countdown; i > 0; i--) {
      cd.textContent = i;
      cd.hidden = false;
      await sleep(1000);
    }
    cd.textContent = "😁";
    const flash = $("flash");
    flash.classList.add("on");
    setTimeout(() => flash.classList.remove("on"), 400);

    const photo = state.camera.mode === "dslr"
      ? await api("/api/capture", { method: "POST" })
      : await grabWebcamFrame();
    openReview(photo);
  } catch (err) {
    toast(err.message, 6000);
  } finally {
    cd.hidden = true;
    busy = false;
  }
}

function openReview(photo) {
  current = photo;
  copies = 1;
  $("copies").textContent = copies;
  $("reviewImg").src = photo.url;
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
    toast(`🖨️ ${r.copies} Ausdruck(e) unterwegs!`);
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
  if (!photos.length) g.textContent = "Noch keine Fotos.";
  show("galleryScreen");
}

// ------------------------------------------------------------------ Start
async function init() {
  state = await api("/api/state");
  document.title = state.event_name;
  $("printGroup").hidden = !state.print_enabled;
  $("shareBtn").hidden = !state.share_enabled;

  if (state.camera.mode === "dslr") startDslrPreview();
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
  });
  // Jede Berührung setzt den Rückkehr-Timer zurück
  document.addEventListener("pointerdown", () => {
    const active = document.querySelector(".screen.active");
    if (active && active.id !== "liveScreen") show(active.id);
  });
}

init().catch((err) => toast(err.message, 10000));
