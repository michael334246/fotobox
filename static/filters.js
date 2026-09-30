// Fotobox – Farb- und Gesichtsfilter (live in der Vorschau und auf dem fertigen Foto)
// Die Gesichtserkennung (MediaPipe) liegt in static/vendor und funktioniert ohne Internet.

const COLOR_FILTERS = [
  { id: "none", label: "Original", icon: "🙂", css: "none" },
  { id: "bw", label: "Schwarz-Weiss", icon: "🖤", css: "grayscale(1) contrast(1.12)" },
  { id: "vintage", label: "Vintage", icon: "📜", css: "sepia(0.55) contrast(1.05) saturate(0.9) brightness(1.05)" },
  { id: "warm", label: "Warm", icon: "🌅", css: "saturate(1.15)", tint: "rgba(255, 140, 40, 0.25)" },
  { id: "cool", label: "Kühl", icon: "❄️", css: "saturate(0.95)", tint: "rgba(40, 120, 255, 0.25)" },
  { id: "pop", label: "Pop", icon: "🌈", css: "contrast(1.2) saturate(1.6)" },
  { id: "dream", label: "Verträumt", icon: "✨", css: "brightness(1.08) contrast(0.9) saturate(1.2) blur(0.6px)" },
];

const FACE_FILTERS = [
  { id: "none", label: "Keiner", icon: "🚫" },
  { id: "dog", label: "Hund", icon: "🐶" },
  { id: "bunny", label: "Hase", icon: "🐰" },
  { id: "glasses", label: "Sonnenbrille", icon: "😎" },
  { id: "partyhat", label: "Partyhut", icon: "🥳" },
  { id: "crown", label: "Krone", icon: "👑" },
  { id: "mustache", label: "Schnauz", icon: "🥸" },
];

let colorFilter = COLOR_FILTERS[0];
let faceFilter = FACE_FILTERS[0];
let detector = null;
let detectorLoading = null;
let lastDetect = 0;
const workCanvas = document.createElement("canvas");  // Arbeitsfläche der Live-Vorschau

function filtersActive() {
  return colorFilter.id !== "none" || faceFilter.id !== "none";
}

// ------------------------------------------------------------------ Gesichtserkennung
function loadDetector() {
  if (!detectorLoading) {
    detectorLoading = (async () => {
      const { FilesetResolver, FaceDetector } = await import("/static/vendor/mediapipe/vision_bundle.mjs");
      const fileset = await FilesetResolver.forVisionTasks("/static/vendor/mediapipe/wasm");
      const options = (delegate) => ({
        baseOptions: { modelAssetPath: "/static/vendor/mediapipe/blaze_face_short_range.tflite", delegate },
        runningMode: "VIDEO",
        minDetectionConfidence: 0.5,
      });
      try {
        detector = await FaceDetector.createFromOptions(fileset, options("GPU"));
      } catch (_) {
        detector = await FaceDetector.createFromOptions(fileset, options("CPU"));
      }
    })();
  }
  return detectorLoading;
}

const cropCanvas = document.createElement("canvas");

function detect(src) {
  lastDetect = Math.max(performance.now(), lastDetect + 1);  // Zeitstempel müssen steigen
  return detector.detectForVideo(src, lastDetect).detections;
}

// Zweistufig: erst Gesichter finden, dann jeden Gesichtsausschnitt vergrössert nochmals auswerten –
// bei kleinen Gesichtern im Kamerabild liegen Augen/Nase/Mund sonst deutlich daneben.
function detectFaces(src, w, h) {
  if (!detector || faceFilter.id === "none") return [];
  const sx = w / (src.videoWidth || src.naturalWidth || src.width);
  const sy = h / (src.videoHeight || src.naturalHeight || src.height);
  const faces = [];
  for (const first of detect(src).slice(0, 4)) {
    const b = first.boundingBox;
    const size = Math.max(b.width, b.height) * 2;
    const x0 = b.originX + b.width / 2 - size / 2, y0 = b.originY + b.height / 2 - size / 2;
    cropCanvas.width = cropCanvas.height = 256;
    cropCanvas.getContext("2d").drawImage(src, x0, y0, size, size, 0, 0, 256, 256);
    const d = detect(cropCanvas)[0] || first;
    const pts = d.keypoints.map((k) => (d === first
      ? { x: k.x * w, y: k.y * h }
      : { x: (x0 + k.x * size) * sx, y: (y0 + k.y * size) * sy }));
    const [a, c] = pts[0].x < pts[1].x ? [pts[0], pts[1]] : [pts[1], pts[0]];
    faces.push({ left: a, right: c, nose: pts[2], mouth: pts[3] });
  }
  return faces;
}

// ------------------------------------------------------------------ Gesichtsfilter zeichnen
// Gezeichnet wird in einem Koordinatensystem pro Gesicht: Ursprung zwischen den Augen,
// Einheit u = Augenabstand, x nach rechts, y nach unten (gedreht wie der Kopf).
function drawFace(ctx, face) {
  const cx = (face.left.x + face.right.x) / 2;
  const cy = (face.left.y + face.right.y) / 2;
  const u = Math.hypot(face.right.x - face.left.x, face.right.y - face.left.y);
  const angle = Math.atan2(face.right.y - face.left.y, face.right.x - face.left.x);
  const local = (p) => {
    const dx = p.x - cx, dy = p.y - cy;
    return { x: (dx * Math.cos(angle) + dy * Math.sin(angle)) / u, y: (-dx * Math.sin(angle) + dy * Math.cos(angle)) / u };
  };
  const nose = local(face.nose);
  const mouth = local(face.mouth);
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(angle);
  ctx.scale(u, u);
  const ellipse = (x, y, rx, ry, rot, fill) => {
    ctx.beginPath();
    ctx.ellipse(x, y, rx, ry, rot, 0, Math.PI * 2);
    ctx.fillStyle = fill;
    ctx.fill();
  };

  if (faceFilter.id === "dog") {
    for (const side of [-1, 1]) {
      ellipse(side * 1.05, -1.2, 0.42, 0.75, side * 0.35, "#7a4a2a");
      ellipse(side * 1.05, -1.15, 0.24, 0.5, side * 0.35, "#f4a6b8");
    }
    ellipse(0, mouth.y + 0.3, 0.2, 0.3, 0, "#ff6b8b");
    ellipse(nose.x, nose.y, 0.3, 0.2, 0, "#222");
    ellipse(nose.x - 0.08, nose.y - 0.06, 0.08, 0.05, 0, "rgba(255,255,255,0.7)");
  } else if (faceFilter.id === "bunny") {
    for (const side of [-1, 1]) {
      ellipse(side * 0.5, -2.0, 0.28, 0.95, side * 0.15, "#ffffff");
      ellipse(side * 0.5, -1.95, 0.14, 0.72, side * 0.15, "#ffc0d0");
    }
    ellipse(nose.x, nose.y, 0.14, 0.1, 0, "#ff8fab");
    ctx.strokeStyle = "rgba(40,40,40,0.8)";
    ctx.lineWidth = 0.03;
    for (const side of [-1, 1]) {
      for (const dy of [-0.08, 0.04, 0.16]) {
        ctx.beginPath();
        ctx.moveTo(nose.x + side * 0.2, nose.y + dy / 2);
        ctx.lineTo(nose.x + side * 0.85, nose.y + dy);
        ctx.stroke();
      }
    }
  } else if (faceFilter.id === "glasses") {
    ctx.strokeStyle = "#111";
    ctx.lineWidth = 0.07;
    for (const side of [-1, 1]) {
      ctx.beginPath();
      ctx.roundRect(side * 0.5 - 0.42, -0.26, 0.84, 0.54, 0.2);
      ctx.fillStyle = "rgba(10,12,24,0.92)";
      ctx.fill();
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(side * 0.5 - 0.25, -0.12);
      ctx.lineTo(side * 0.5 - 0.05, -0.18);
      ctx.strokeStyle = "rgba(255,255,255,0.45)";
      ctx.stroke();
      ctx.strokeStyle = "#111";
      ctx.beginPath();
      ctx.moveTo(side * 0.92, -0.1);
      ctx.lineTo(side * 1.1, -0.05);
      ctx.stroke();
    }
    ctx.beginPath();
    ctx.moveTo(-0.08, -0.12);
    ctx.quadraticCurveTo(0, -0.2, 0.08, -0.12);
    ctx.stroke();
  } else if (faceFilter.id === "partyhat") {
    ctx.beginPath();
    ctx.moveTo(-0.65, -1.3);
    ctx.lineTo(0.65, -1.3);
    ctx.lineTo(0, -2.9);
    ctx.closePath();
    ctx.fillStyle = "#3b82f6";
    ctx.fill();
    ctx.save();
    ctx.clip();
    ctx.fillStyle = "#ffd166";
    for (let i = -4; i < 6; i++) {
      ctx.beginPath();
      ctx.moveTo(-1, -1.3 - i * 0.35);
      ctx.lineTo(1, -1.6 - i * 0.35);
      ctx.lineTo(1, -1.75 - i * 0.35);
      ctx.lineTo(-1, -1.45 - i * 0.35);
      ctx.fill();
    }
    ctx.restore();
    ellipse(0, -2.9, 0.22, 0.22, 0, "#ff4d8d");
    ellipse(0, -1.3, 0.72, 0.1, 0, "#ff4d8d");
  } else if (faceFilter.id === "crown") {
    ctx.beginPath();
    const pts = [[-0.85, -1.05], [-0.85, -1.75], [-0.45, -1.4], [0, -1.95], [0.45, -1.4], [0.85, -1.75], [0.85, -1.05]];
    pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.closePath();
    ctx.fillStyle = "#f5c542";
    ctx.fill();
    ctx.lineWidth = 0.05;
    ctx.strokeStyle = "#c98f00";
    ctx.stroke();
    [[-0.45, -1.25, "#e63946"], [0, -1.25, "#3b82f6"], [0.45, -1.25, "#06d6a0"]].forEach(([x, y, c]) =>
      ellipse(x, y, 0.1, 0.1, 0, c));
  } else if (faceFilter.id === "mustache") {
    const y = nose.y * 0.45 + mouth.y * 0.55;
    for (const side of [-1, 1]) {
      ellipse(side * 0.26, y, 0.3, 0.12, side * -0.25, "#3b2314");
      ellipse(side * 0.55, y - 0.1, 0.1, 0.1, 0, "#3b2314");
    }
  }
  ctx.restore();
}

// Filter auf ein Bild anwenden (Farbe, Tönung, Gesichtsfilter)
function paintFiltered(ctx, src, w, h, faces) {
  ctx.filter = colorFilter.css;
  ctx.drawImage(src, 0, 0, w, h);
  ctx.filter = "none";
  if (colorFilter.tint) {
    ctx.globalCompositeOperation = "soft-light";
    ctx.fillStyle = colorFilter.tint;
    ctx.fillRect(0, 0, w, h);
    ctx.globalCompositeOperation = "source-over";
  }
  faces.forEach((f) => drawFace(ctx, f));
}

// Live-Vorschau: gefiltertes Kamerabild (verkleinert, damit es flüssig bleibt)
function filteredPreview(src, sw, sh) {
  if (!filtersActive() || !sw) return src;
  const scale = Math.min(1, 960 / sw);
  const w = Math.round(sw * scale), h = Math.round(sh * scale);
  if (workCanvas.width !== w || workCanvas.height !== h) [workCanvas.width, workCanvas.height] = [w, h];
  paintFiltered(workCanvas.getContext("2d"), src, w, h, detectFaces(src, w, h));
  return workCanvas;
}

// Aufnahme: Filter in voller Auflösung ins Foto einrechnen
function applyFilters(canvas) {
  if (!filtersActive()) return canvas;
  const out = document.createElement("canvas");
  [out.width, out.height] = [canvas.width, canvas.height];
  paintFiltered(out.getContext("2d"), canvas, out.width, out.height, detectFaces(canvas, out.width, out.height));
  return out;
}

// ------------------------------------------------------------------ Auswahl
function setupFilters(enabled) {
  if (!enabled) return;
  $("filterBtn").hidden = false;
  const chips = (box, list, current, onPick) => {
    box.innerHTML = "";
    for (const f of list) {
      const b = document.createElement("button");
      b.className = "chip" + (f === current ? " selected" : "");
      b.innerHTML = `<span>${f.icon}</span>`;
      b.append(f.label);
      b.onclick = () => {
        onPick(f);
        box.querySelectorAll(".chip").forEach((c) => c.classList.toggle("selected", c === b));
        updateFilterName();
      };
      box.appendChild(b);
    }
  };
  chips($("colorFilters"), COLOR_FILTERS, colorFilter, (f) => (colorFilter = f));
  chips($("faceFilters"), FACE_FILTERS, faceFilter, (f) => {
    faceFilter = f;
    if (f.id !== "none" && !detector) {
      toast("Gesichtsfilter wird geladen …", 4000);
      loadDetector().then(() => ($("toast").hidden = true)).catch(() =>
        toast("Gesichtsfilter sind in diesem Browser nicht verfügbar (Chrome oder Edge verwenden).", 6000));
    }
  });
  $("filterBtn").onclick = () => ($("filterModal").hidden = false);
  $("filterClose").onclick = () => ($("filterModal").hidden = true);
}

function updateFilterName() {
  const parts = [colorFilter, faceFilter].filter((f) => f.id !== "none").map((f) => f.label);
  $("filterName").textContent = parts.join(" + ") || "Original";
}
