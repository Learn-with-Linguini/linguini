// Overlay for the launch film. seek(t) draws the frame at time t (seconds) and
// depends on nothing else, so frames can be rendered in any order.
const W = 1920, H = 1080;
const $ = (id) => document.getElementById(id);
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const expoOut = (x) => (x >= 1 ? 1 : 1 - Math.pow(2, -10 * x));
const cubicOut = (x) => 1 - Math.pow(1 - x, 3);
const lerp = (a, b, k) => a + (b - a) * k;
const lerpBox = (a, b, k) => a.map((v, i) => lerp(v, b[i], k));

const LOCK = { act1: 0.42, act2a: 0.3, act2b: 0.17, act2c: 0.09, final: 0.42 };
const TAG_LIMIT = 900;
const INTRO_BOX = [900, 480, 1020, 600];
let T, B, FPS;

function shotAt(t) {
  for (let i = T.shots.length - 1; i >= 0; i--) if (t >= T.shots[i].start - 1e-6) return i;
  return -1;
}

function rawBox(t) {
  const f = clamp(Math.round(t * FPS), 0, B.length - 1);
  return B[f];
}

function headlineAt(t) {
  return T.headline.find((h) => t >= h.start - 1e-6 && t < h.end - 1e-6);
}

function targetBox(t, i) {
  const s = T.shots[i];
  let b = rawBox(Math.min(t, s.start + s.dur - 1 / FPS)).slice();
  // keep clear of the headline above and leave room for the word below
  const top = headlineAt(t) ? 180 : 40;
  b = [Math.max(b[0], 40), Math.max(b[1], top), Math.min(b[2], W - 40), Math.min(b[3], TAG_LIMIT)];
  if (b[3] - b[1] < 140) b[1] = Math.max(top, b[3] - 140);
  return b;
}

function brackets(b, alpha) {
  const [x0, y0, x1, y1] = b;
  const L = clamp(Math.min(x1 - x0, y1 - y0) * 0.16, 16, 46);
  const d = [
    `M${x0},${y0 + L}V${y0}H${x0 + L}`, `M${x1 - L},${y0}H${x1}V${y0 + L}`,
    `M${x1},${y1 - L}V${y1}H${x1 - L}`, `M${x0 + L},${y1}H${x0}V${y1 - L}`,
  ].join("");
  $("brackets").setAttribute("d", d);
  $("box").style.opacity = alpha;
}

function drawBox(t) {
  const i = shotAt(t);
  if (i < 0) {
    // the viewfinder wakes: two blinks on the intro notes
    const on = (t >= T.intro_note && t < T.intro_note + 0.2) || t >= T.intro_note + T.beat;
    const k = t >= T.intro_note + T.beat ? expoOut((t - T.intro_note - T.beat) / 0.25) : 1;
    brackets(lerpBox([930, 510, 990, 570], INTRO_BOX, k), on ? 0.9 : 0);
    return null;
  }
  const s = T.shots[i];
  const lock = LOCK[s.section];
  const u = clamp((t - s.start) / lock);
  const e = expoOut(u);
  const from = i === 0 ? INTRO_BOX : targetBox(s.start - 1 / FPS, i - 1);
  const to = targetBox(t, i);
  let b = lerpBox(from, to, e);
  // overshoot then settle, like autofocus hunting
  const grow = (1 - e) * 0.08;
  const cx = (b[0] + b[2]) / 2, cy = (b[1] + b[3]) / 2, hw = (b[2] - b[0]) / 2, hh = (b[3] - b[1]) / 2;
  b = [cx - hw * (1 + grow), cy - hh * (1 + grow), cx + hw * (1 + grow), cy + hh * (1 + grow)];
  brackets(b, 0.92);
  return { s, b: to, u, lock };
}

function drawTag(t, st) {
  const tag = $("tag");
  if (!st) { tag.style.opacity = 0; return; }
  const { s, b } = st;
  $("word").textContent = s.word;
  $("gloss").textContent = s.gloss;
  const w = tag.offsetWidth, h = tag.offsetHeight;
  const cx = clamp((b[0] + b[2]) / 2, w / 2 + 60, W - w / 2 - 60);
  const y = b[3] + 24;
  const fast = s.section === "act2b" || s.section === "act2c";
  const k = fast ? 1 : cubicOut(clamp((t - s.start - st.lock * 0.35) / 0.35));
  tag.style.opacity = k;
  tag.style.transform = `translate(${cx - w / 2}px, ${y + (1 - k) * 10}px)`;
}

function drawHeadline(t) {
  const h = headlineAt(t);
  const el = $("headline");
  const scrim = $("topscrim");
  const on = T.headline[0].start, off = T.headline[T.headline.length - 1].end;
  scrim.style.opacity = t < off ? cubicOut(clamp((t - on) / 0.3)) : 0;
  if (!h) { el.style.opacity = 0; return; }
  el.textContent = h.text;
  const k = cubicOut(clamp((t - h.start) / 0.22));
  el.style.opacity = k;
  el.style.transform = `translateY(${(1 - k) * 8}px)`;
}

let strandLen = 0;
function layoutStrand() {
  const wm = $("wm"), F = 236;
  const u = wm.getExtentOfChar(4), last = wm.getExtentOfChar(7);
  const base = 520;
  const x0 = u.x + F * 0.02;
  // end just past the last i with a small upward flick, clear of the letter
  const x1 = last.x + last.width + F * 0.12;
  const pts = [];
  const n = 90;
  for (let k = 0; k <= n; k++) {
    const q = k / n;
    const x = lerp(x0, x1, q);
    let y = base + F * 0.2 + Math.sin(q * Math.PI * 3 + 0.2) * F * 0.045;
    const rise = clamp((q - 0.86) / 0.14);
    y -= Math.pow(rise, 1.8) * F * 0.13;
    pts.push([x, y]);
  }
  const d = pts.map((p, k) => `${k ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("");
  const strand = $("strand");
  strand.setAttribute("d", d);
  strand.setAttribute("stroke-width", (F * 0.082).toFixed(1));
  strandLen = strand.getTotalLength();
  strand.style.strokeDasharray = strandLen;
}

function drawEnd(t) {
  const end = $("end");
  if (t < T.cut) { end.style.opacity = 0; return; }
  // Never fully opaque: Chromium saves opaque frames as RGB PNGs, and a switch
  // from RGBA to RGB mid-sequence makes ffmpeg drop frames. 0.996 over the
  // black plate is invisible.
  end.style.opacity = 0.996 * (1 - clamp((t - T.fade_out) / (T.end - T.fade_out - 0.1)));
  const g = cubicOut(clamp((t - T.logo_chord + 0.2) / 3.2));
  $("glow").style.opacity = g * 0.85;
  $("glow").style.transform = `translateY(${(1 - g) * 90}px)`;
  const m = cubicOut(clamp((t - T.logo_chord) / 1.0));
  const wm = $("wm");
  wm.style.opacity = m;
  wm.style.filter = `blur(${(1 - m) * 10}px)`;
  wm.setAttribute("transform", `translate(0 ${(1 - m) * 14})`);
  const sq = cubicOut(clamp((t - T.logo_chord - 0.25) / 1.1));
  $("strand").style.strokeDashoffset = strandLen * (1 - sq);
  $("strand").setAttribute("transform", `translate(0 ${(1 - m) * 14})`);
  const tl = cubicOut(clamp((t - T.tagline) / 0.9));
  $("tagline").style.opacity = tl * 0.94;
  $("tagline").style.transform = `translateY(${(1 - tl) * 12}px)`;
  const ph = cubicOut(clamp((t - T.ph_line) / 0.8));
  $("ph").style.opacity = ph * 0.62;
}

window.seek = (t) => {
  const st = t < T.cut ? drawBox(t) : (brackets([0, 0, 0, 0], 0), null);
  drawTag(t, t < T.cut ? st : null);
  drawHeadline(t);
  drawEnd(t);
};

window.ready = (async () => {
  T = await (await fetch("timeline.json")).json();
  const bx = await (await fetch("boxes.json")).json();
  B = bx.boxes; FPS = bx.fps;
  await document.fonts.load('72px "Instrument Serif"');
  await document.fonts.load('800 236px "Baloo 2"');
  await document.fonts.load('800 17px "Nunito Sans"');
  await document.fonts.ready;
  layoutStrand();
  const q = new URLSearchParams(location.search);
  if (q.has("t")) { document.body.classList.add("preview"); window.seek(parseFloat(q.get("t"))); }
  return true;
})();
