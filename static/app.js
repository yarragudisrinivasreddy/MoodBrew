// MoodBrew front end. Face reading runs on-device with MediaPipe; only 4 numbers leave the phone.
const VISION = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";
const MODEL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";
const ROUND_MS = 3500;
const RING_LEN = 339.3;

const $ = (sel) => document.querySelector(sel);
const clamp = (v) => Math.max(0, Math.min(1, v));
const avg = (...n) => n.reduce((a, b) => a + b, 0) / n.length;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const table = (new URLSearchParams(location.search).get("t") || "").replace(/[^A-Za-z0-9 -]/g, "").slice(0, 12) || null;
const state = { stream: null, landmarker: null, cancelled: false, picks: null };

function clientId() {
  try {
    let id = localStorage.getItem("mb_cid");
    if (!id) { id = crypto.randomUUID(); localStorage.setItem("mb_cid", id); }
    return id;
  } catch { return "anon-" + Math.random().toString(36).slice(2, 12); }
}

const VIBES = {
  spark: { name: "Spark", d: "Bright, quick, up for anything.", scores: { joy: 0.85, surprise: 0.5, calm: 0.1, play: 0.2 } },
  zen: { name: "Zen", d: "Quiet focus, slow sips.", scores: { joy: 0.2, surprise: 0.05, calm: 0.95, play: 0 } },
  cozy: { name: "Cozy", d: "Warm, soft, in no rush.", scores: { joy: 0.55, surprise: 0.1, calm: 0.6, play: 0.05 } },
  chaos: { name: "Chaos", d: "Playful and a little unhinged.", scores: { joy: 0.3, surprise: 0.5, calm: 0, play: 0.95 } },
};

// Each challenge turns blendshape scores (0..1) into a live value and a final score.
const act = (b) => Math.max(avg(b.mouthSmileLeft || 0, b.mouthSmileRight || 0), b.jawOpen || 0, b.browInnerUp || 0, avg(b.browDownLeft || 0, b.browDownRight || 0));
const CHALLENGES = [
  { key: "joy", text: "Biggest smile you've got", live: (b) => clamp(avg(b.mouthSmileLeft || 0, b.mouthSmileRight || 0) * 1.25), final: (s) => s.peak },
  { key: "surprise", text: "Look amazed!", live: (b) => clamp(avg(b.browInnerUp || 0, b.jawOpen || 0) * 1.6), final: (s) => s.peak },
  { key: "calm", text: "Now, perfectly calm", live: (b) => 1 - clamp(act(b) * 2), final: (s) => 1 - clamp(s.avgAct * 2) },
  { key: "play", text: "Give us a wink", live: (b) => clamp(Math.abs((b.eyeBlinkLeft || 0) - (b.eyeBlinkRight || 0)) * 1.3), final: (s) => s.peak },
];

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}
function show(id) {
  for (const s of ["intro", "stage", "tap", "result"]) $("#" + s).hidden = s !== id;
  if (id === "result" || id === "stage" || id === "tap") $("#" + id).scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
}
function say(msg) { $("#status").textContent = msg; }

async function loadLandmarker() {
  const { FaceLandmarker, FilesetResolver } = await import(`${VISION}/vision_bundle.mjs`);
  const fileset = await FilesetResolver.forVisionTasks(`${VISION}/wasm`);
  const options = (delegate) => ({
    baseOptions: { modelAssetPath: MODEL, delegate },
    runningMode: "VIDEO", numFaces: 1, outputFaceBlendshapes: true,
  });
  try { return await FaceLandmarker.createFromOptions(fileset, options("GPU")); }
  catch { return FaceLandmarker.createFromOptions(fileset, options("CPU")); }
}

function stopCamera() {
  if (state.stream) { state.stream.getTracks().forEach((t) => t.stop()); state.stream = null; }
  $("#cam").srcObject = null;
}

function readBlendshapes(video, now) {
  const res = state.landmarker.detectForVideo(video, now);
  const cats = res.faceBlendshapes && res.faceBlendshapes[0] && res.faceBlendshapes[0].categories;
  if (!cats) return null;
  const out = {};
  for (const c of cats) out[c.categoryName] = c.score;
  return out;
}

function runRound(ch, video) {
  return new Promise((resolve) => {
    const start = performance.now();
    let peak = 0, sum = 0, n = 0;
    const tick = (now) => {
      if (state.cancelled) return resolve(null);
      const t = (now - start) / ROUND_MS;
      const b = readBlendshapes(video, now);
      if (b) { const v = ch.live(b); peak = Math.max(peak, v); sum += act(b); n += 1; $("#meter-fill").style.width = `${Math.round(v * 100)}%`; }
      $("#ring").style.strokeDashoffset = String(RING_LEN * (1 - Math.min(t, 1)));
      if (t < 1) requestAnimationFrame(tick);
      else resolve({ seen: n > 0, score: n ? clamp(ch.final({ peak, avgAct: sum / n })) : 0 });
    };
    requestAnimationFrame(tick);
  });
}

async function startCamera() {
  state.cancelled = false;
  show("stage");
  say("Asking for your camera. Allow it to play.");
  $("#challenge").textContent = "";
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: { ideal: 640 } }, audio: false });
    const video = $("#cam");
    video.srcObject = state.stream;
    await video.play();
    say("Warming up the face reader...");
    state.landmarker = state.landmarker || (await loadLandmarker());
  } catch {
    stopCamera();
    say("");
    startTap("We couldn't open the camera, so here is the tap version.");
    return;
  }
  const rounds = [...CHALLENGES].sort(() => Math.random() - 0.5).slice(0, 3);
  const scores = { joy: 0, surprise: 0, calm: 0, play: 0 };
  let unseen = 0;
  for (let i = 0; i < rounds.length; i += 1) {
    const ch = rounds[i];
    $("#round-label").textContent = `Round ${i + 1} of ${rounds.length}`;
    $("#challenge").textContent = "Get ready...";
    $("#meter-fill").style.width = "0%";
    $("#ring").style.strokeDashoffset = String(RING_LEN);
    say("");
    await wait(1100);
    if (state.cancelled) return;
    $("#challenge").textContent = ch.text;
    const out = await runRound(ch, $("#cam"));
    if (!out) return;
    scores[ch.key] = out.score;
    if (!out.seen) unseen += 1;
  }
  stopCamera();
  if (unseen === rounds.length) { startTap("We couldn't see a face clearly. Pick your vibe instead."); return; }
  await submit(scores);
}

function startTap(message) {
  state.cancelled = true;
  stopCamera();
  const grid = $("#tap-grid");
  grid.replaceChildren();
  for (const [key, v] of Object.entries(VIBES)) {
    const tile = el("button", "tile v-" + key);
    tile.type = "button";
    tile.setAttribute("role", "radio");
    tile.setAttribute("aria-checked", "false");
    tile.append(el("div", "mini v-" + key), el("strong", "", v.name), el("span", "d", v.d));
    tile.addEventListener("click", () => submit(v.scores));
    grid.append(tile);
  }
  $("#tap-title").textContent = message || "Pick the vibe that feels like you right now";
  show("tap");
}

async function submit(scores) {
  try {
    const res = await fetch("/api/vibe", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: clientId(), table, ...scores }),
    });
    if (!res.ok) throw new Error("bad response");
    render(await res.json());
  } catch {
    startTap("Something hiccuped on our side. Pick your vibe to try again.");
  }
}

function render(r) {
  state.picks = r;
  const v = VIBES[r.vibe];
  const card = $("#vibecard");
  card.className = "vibecard v-" + r.vibe;
  $("#result-orb").className = "vibecard__orb mini v-" + r.vibe;
  $("#result-eyebrow").textContent = "Your vibe";
  $("#result-title").textContent = v.name;
  $("#result-line").textContent = r.line;
  $("#result-points").textContent = String(r.points);
  $("#result-badge").textContent = r.badge;
  const list = $("#picks");
  list.replaceChildren();
  for (const [label, item] of [["Drink", r.drink], ["Snack", r.snack]]) {
    const li = el("li", "pick");
    li.append(el("span", "k", label), el("strong", "", item.name), el("span", "p", `₹${item.price}`), el("span", "b", item.blurb));
    list.append(li);
  }
  $("#order-status").textContent = "";
  $("#order-btn").disabled = false;
  show("result");
  loadBoard();
}

async function order() {
  const btn = $("#order-btn");
  btn.disabled = true;
  try {
    const res = await fetch("/api/order", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ table, item_ids: [state.picks.drink.id, state.picks.snack.id] }),
    });
    if (!res.ok) throw new Error("bad response");
    const o = await res.json();
    $("#order-status").textContent = `Sent. Ready in about ${o.eta_minutes} minutes. Total ₹${o.total}.`;
  } catch {
    $("#order-status").textContent = "Couldn't reach the bar. Please try again.";
    btn.disabled = false;
  }
}

async function loadBoard() {
  try {
    const [board, w] = await Promise.all([fetch("/api/leaderboard").then((r) => r.json()), fetch("/api/wait").then((r) => r.json())]);
    const ol = $("#board");
    ol.replaceChildren();
    if (!board.length) ol.append(el("li", "", "No scores yet. Be the first table on the board."));
    for (const row of board) {
      const li = el("li");
      li.append(el("span", "", `Table ${row.table}`), el("span", "", `${row.points} pts`));
      ol.append(li);
    }
    $("#wait-note").textContent = `The bar is ${w.status} right now, about ${w.wait_minutes} minutes for a new order.`;
  } catch { /* leaderboard is optional */ }
}

$("#start-camera").addEventListener("click", startCamera);
$("#start-tap").addEventListener("click", () => startTap());
$("#cancel-game").addEventListener("click", () => startTap());
$("#order-btn").addEventListener("click", order);
$("#again-btn").addEventListener("click", () => { state.cancelled = false; show("intro"); window.scrollTo({ top: 0 }); });
if (table) { const chip = $("#table-chip"); chip.textContent = `Table ${table}`; chip.hidden = false; }
loadBoard();
