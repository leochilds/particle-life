// Particle Life — full-screen live viewer.
//
// Runs the simulation continuously on a Canvas, shows a live "vitality" meter,
// detects when a universe has gone quiet, and can quick-search for a fresh
// lively one (optionally auto-replacing boring universes). Universes are
// shareable via the URL hash.

import { Simulation, PALETTE, mulberry32, randomMatrix, vitalityParts } from './sim.js';

const canvas = document.getElementById('view');
const ctx = canvas.getContext('2d', { alpha: false });

// -- tunables ---------------------------------------------------------------
const BORING_THRESHOLD = 0.16;   // smoothed vitality below this == quiet
const BORING_SECONDS = 5;        // ...sustained this long == "gone quiet"
const AUTO_GRACE_SECONDS = 2;    // extra wait before auto-replace kicks in
const SEARCH_CANDIDATES = 12;    // universes evaluated per quick-search
const SETTLE_STEPS = 120;        // warmup applied before showing a universe

// -- state ------------------------------------------------------------------
let sim;
let glowSprites = [];
let dpr = 1, cssW = 0, cssH = 0, scale = 1;
let paused = false;
let searching = false;
let autoReplace = false;

let vitality = 0.5;              // EMA-smoothed score for the meter
let parts = { clustering: 0, motion: 0, heterogeneity: 0, score: 0 };
let occSnapshot = null;
let frame = 0;
let quietFrames = 0;            // consecutive frames below threshold
let boring = false;

// pointer "stir": x/y in world units, sign +1 repel / -1 attract
const pointer = { active: false, x: 0, y: 0, sign: -1 };
let stirredOnce = false;

// global seeded RNG for matrix generation (re-seeded from time at boot)
let rng = mulberry32(Date.now() & 0xffffffff);

// -- canvas sizing ----------------------------------------------------------
function resize() {
  dpr = Math.min(2, window.devicePixelRatio || 1);
  cssW = window.innerWidth;
  cssH = window.innerHeight;
  canvas.width = Math.round(cssW * dpr);
  canvas.height = Math.round(cssH * dpr);
  canvas.style.width = cssW + 'px';
  canvas.style.height = cssH + 'px';
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  scale = cssH;                 // world height == 1, so 1 world unit == cssH px
  const worldW = cssW / cssH;   // aspect-matched torus width
  buildSprites();
  if (sim) sim.resize(worldW, 1.0);
}

// Pre-render a soft radial glow per palette color.
function buildSprites() {
  const glowR = Math.max(9, Math.round(cssH * 0.013));
  const size = glowR * 2;
  glowSprites = PALETTE.map(([r, g, b]) => {
    const c = document.createElement('canvas');
    c.width = c.height = size;
    const g2 = c.getContext('2d');
    const grad = g2.createRadialGradient(glowR, glowR, 0, glowR, glowR, glowR);
    // a bright tight core fading into a soft wide halo, so dense clusters bloom
    grad.addColorStop(0.00, `rgba(255,255,255,0.95)`);
    grad.addColorStop(0.18, `rgba(${r},${g},${b},0.95)`);
    grad.addColorStop(0.45, `rgba(${r},${g},${b},0.40)`);
    grad.addColorStop(1.00, `rgba(${r},${g},${b},0)`);
    g2.fillStyle = grad;
    g2.fillRect(0, 0, size, size);
    return { canvas: c, r: glowR };
  });
}

// -- rendering --------------------------------------------------------------
function draw() {
  ctx.fillStyle = '#04060a';
  ctx.fillRect(0, 0, cssW, cssH);
  ctx.globalCompositeOperation = 'lighter';
  const { px, py, species, n } = sim;
  for (let i = 0; i < n; i++) {
    const sp = glowSprites[species[i] % glowSprites.length];
    ctx.drawImage(sp.canvas, px[i] * scale - sp.r, py[i] * scale - sp.r);
  }
  ctx.globalCompositeOperation = 'source-over';
}

// -- vitality / boredom -----------------------------------------------------
function updateVitality() {
  const occ = sim.occupancy(32, 32);
  if (!occSnapshot || frame % 30 === 0) {
    parts = vitalityParts(occ, occSnapshot, sim.n, sim.meanSpeed());
    occSnapshot = occ;
  } else {
    parts = vitalityParts(occ, occSnapshot, sim.n, sim.meanSpeed());
  }
  vitality += (parts.score - vitality) * 0.04;   // EMA smoothing
  renderMeter();

  if (vitality < BORING_THRESHOLD) quietFrames++; else quietFrames = 0;
  const wasBoring = boring;
  boring = quietFrames > BORING_SECONDS * 60;
  if (boring && !wasBoring) onBoring();
  if (!boring && wasBoring) hideQuiet();

  if (boring && autoReplace && !searching &&
      quietFrames > (BORING_SECONDS + AUTO_GRACE_SECONDS) * 60) {
    newUniverse(true);
  }
}

function renderMeter() {
  document.getElementById('vital-fill').style.width = (vitality * 100).toFixed(1) + '%';
  document.getElementById('vital-num').textContent = vitality.toFixed(2);
  setBar('bar-clu', parts.clustering);
  setBar('bar-mot', parts.motion);
  setBar('bar-het', parts.heterogeneity);
  const m = document.getElementById('meter');
  m.classList.toggle('quiet', vitality < BORING_THRESHOLD);
}
function setBar(id, v) { document.getElementById(id).style.width = (v * 100).toFixed(0) + '%'; }

function onBoring() {
  document.getElementById('quiet').classList.add('show');
  document.body.classList.add('is-quiet');
}
function hideQuiet() {
  document.getElementById('quiet').classList.remove('show');
  document.body.classList.remove('is-quiet');
}

// -- universe generation ----------------------------------------------------
// Quickly score a candidate matrix on a small headless sim.
function scoreCandidate(matrix, species) {
  const worldW = cssW / cssH;
  const s = new Simulation({ n: 450, species, width: worldW, height: 1,
    matrix, seed: (rng() * 1e9) | 0 });
  for (let i = 0; i < 110; i++) s.step();
  const occA = s.occupancy(24, 24);
  for (let i = 0; i < 40; i++) s.step();
  const occB = s.occupancy(24, 24);
  return vitalityParts(occB, occA, s.n, s.meanSpeed()).score;
}

async function findLivelyMatrix() {
  const overlay = document.getElementById('search');
  overlay.classList.add('show');
  let best = null;
  for (let k = 0; k < SEARCH_CANDIDATES; k++) {
    const species = 4 + ((rng() * 3) | 0);            // 4..6 species
    const m = randomMatrix(species, rng);
    const score = scoreCandidate(m, species);
    if (!best || score > best.score) best = { m, species, score };
    document.getElementById('search-bar').style.width =
      (((k + 1) / SEARCH_CANDIDATES) * 100).toFixed(0) + '%';
    document.getElementById('search-best').textContent = best.score.toFixed(2);
    await new Promise(requestAnimationFrame);          // keep UI responsive
  }
  overlay.classList.remove('show');
  return best;
}

async function newUniverse(searched) {
  if (searching) return;
  searching = true;
  let matrix, species;
  if (searched) {
    const best = await findLivelyMatrix();
    matrix = best.m; species = best.species;
  } else {
    species = 4 + ((rng() * 3) | 0);
    matrix = randomMatrix(species, rng);
  }
  applyUniverse(matrix, species, true);
  searching = false;
}

function applyUniverse(matrix, species, settle) {
  const worldW = cssW / cssH;
  sim = new Simulation({ n: particleCount(), species, width: worldW, height: 1,
    matrix, seed: (rng() * 1e9) | 0 });
  if (settle) for (let i = 0; i < SETTLE_STEPS; i++) sim.step();
  occSnapshot = null; quietFrames = 0; boring = false; vitality = 0.5;
  hideQuiet();
  writeHash(matrix, species);
}

function particleCount() {
  const area = window.innerWidth * window.innerHeight;
  return Math.max(1000, Math.min(4000, Math.round(area / 620)));
}

// -- share via URL hash -----------------------------------------------------
function writeHash(matrix, species) {
  const bytes = new Uint8Array(1 + matrix.length);
  bytes[0] = species;
  for (let i = 0; i < matrix.length; i++)
    bytes[i + 1] = Math.max(0, Math.min(255, Math.round((matrix[i] + 1) * 127.5)));
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  const b64 = btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  history.replaceState(null, '', '#u=' + b64);
}

function readHash() {
  const m = location.hash.match(/u=([A-Za-z0-9\-_]+)/);
  if (!m) return null;
  try {
    const b64 = m[1].replace(/-/g, '+').replace(/_/g, '/');
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const species = bytes[0];
    const matrix = new Float32Array(species * species);
    for (let i = 0; i < matrix.length; i++) matrix[i] = bytes[i + 1] / 127.5 - 1;
    return { matrix, species };
  } catch (e) { return null; }
}

// -- main loop --------------------------------------------------------------
function loop() {
  if (sim && !paused && !searching) {
    if (pointer.active) {
      const radius = 0.16, strength = 0.05, swirl = 0.012;
      sim.applyImpulse(pointer.x, pointer.y, radius, strength, pointer.sign, swirl);
    }
    sim.step();
    updateVitality();
    frame++;
  }
  if (sim) draw();           // keep drawing (e.g. the settling sim during a search)
  requestAnimationFrame(loop);
}

// -- UI wiring --------------------------------------------------------------
function wireUI() {
  document.getElementById('btn-new').onclick = () => newUniverse(true);
  document.getElementById('quiet-new').onclick = () => newUniverse(true);
  document.getElementById('btn-pause').onclick = togglePause;
  document.getElementById('btn-share').onclick = share;
  const auto = document.getElementById('chk-auto');
  auto.onchange = () => { autoReplace = auto.checked; };

  document.getElementById('btn-about').onclick = () => toggleAbout(true);
  document.getElementById('about-close').onclick = () => toggleAbout(false);
  document.getElementById('about').addEventListener('click', (e) => {
    if (e.target.id === 'about') toggleAbout(false);   // click backdrop to close
  });

  window.addEventListener('keydown', (e) => {
    if (e.code === 'Space') { e.preventDefault(); togglePause(); }
    else if (e.key === 'n') newUniverse(true);
    else if (e.key === 'h') document.body.classList.toggle('hide-ui');
    else if (e.key === 'Escape') toggleAbout(false);
  });
  window.addEventListener('resize', resize);

  wirePointer();
}

// Drag on the canvas to stir the universe. Primary button/touch attracts;
// right-click or the Shift key repels. Tearing structures apart and watching
// them heal is the whole idea made tactile.
function wirePointer() {
  const setFromEvent = (clientX, clientY) => {
    pointer.x = clientX / scale;
    pointer.y = clientY / scale;
  };
  const start = (e) => {
    if (e.target.closest('#controls, #meter, #about, .quiet-card, #btn-about')) return;
    pointer.active = true;
    pointer.sign = (e.button === 2 || e.shiftKey) ? 1 : -1;
    const t = e.touches ? e.touches[0] : e;
    setFromEvent(t.clientX, t.clientY);
    if (!stirredOnce) { stirredOnce = true; document.body.classList.add('stirred'); }
    if (e.cancelable) e.preventDefault();
  };
  const move = (e) => {
    if (!pointer.active) return;
    const t = e.touches ? e.touches[0] : e;
    setFromEvent(t.clientX, t.clientY);
    if (e.cancelable) e.preventDefault();
  };
  const end = () => { pointer.active = false; };

  canvas.addEventListener('mousedown', start);
  window.addEventListener('mousemove', move);
  window.addEventListener('mouseup', end);
  canvas.addEventListener('touchstart', start, { passive: false });
  window.addEventListener('touchmove', move, { passive: false });
  window.addEventListener('touchend', end);
  canvas.addEventListener('contextmenu', (e) => e.preventDefault());
}

function toggleAbout(show) {
  document.getElementById('about').classList.toggle('show', show);
}

function togglePause() {
  paused = !paused;
  document.getElementById('btn-pause').textContent = paused ? '▶ Play' : '❚❚ Pause';
}

async function share() {
  const url = location.href;
  try { await navigator.clipboard.writeText(url); flash('Link copied'); }
  catch (e) { flash('Copy this URL from the address bar'); }
}

function flash(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg; el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 1800);
}

// -- boot -------------------------------------------------------------------
function boot() {
  resize();
  wireUI();
  const fromHash = readHash();
  if (fromHash) applyUniverse(fromHash.matrix, fromHash.species, true);
  else newUniverse(true);
  // ensure a sim exists immediately even while the first search runs
  if (!sim) applyUniverse(randomMatrix(5, rng), 5, true);
  loop();
}

boot();
