// Particle Life — JavaScript engine.
//
// A faithful port of the Python core/engine.py: same piecewise force curve,
// same torus world, same integration. Neighbor search uses a linked-list
// spatial hash grid (head/next arrays) so it runs in ~O(N) on a few thousand
// particles at 60fps. No DOM access here, so it's unit-testable under Node.

export const PALETTE = [
  [255, 89, 94],   // red
  [255, 202, 58],  // yellow
  [138, 201, 38],  // green
  [25, 130, 196],  // blue
  [106, 76, 147],  // purple
  [255, 146, 76],  // orange
  [82, 226, 220],  // cyan
  [240, 240, 240], // white
];

const DEFAULTS = {
  n: 1800,
  species: 5,
  width: 1.0,    // world is a torus of width x height (aspect-matched by caller)
  height: 1.0,
  rMax: 0.075,   // interaction radius
  beta: 0.30,    // hard-core fraction
  forceScale: 4.0,
  friction: 0.85,
  dt: 0.012,
};

// A small seedable PRNG (mulberry32) so universes are reproducible from a seed.
export function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function randomMatrix(species, rng) {
  const m = new Float32Array(species * species);
  for (let i = 0; i < m.length; i++) m[i] = rng() * 2 - 1;
  return m;
}

// Piecewise force as a function of normalized distance r in [0,1].
// r < beta            -> universal repulsion rising to -1 at r=0
// beta <= r <= 1      -> triangular bump of signed strength `a`
function forceCurve(r, a, beta) {
  if (r < beta) return r / beta - 1.0;
  return a * (1.0 - Math.abs(2.0 * r - 1.0 - beta) / (1.0 - beta));
}

export class Simulation {
  constructor(opts = {}) {
    const cfg = { ...DEFAULTS, ...opts };
    this.cfg = cfg;
    this.rng = mulberry32(cfg.seed ?? 1);

    const n = cfg.n;
    this.n = n;
    this.px = new Float32Array(n);
    this.py = new Float32Array(n);
    this.vx = new Float32Array(n);
    this.vy = new Float32Array(n);
    this.species = new Uint8Array(n);

    this.setMatrix(cfg.matrix ?? randomMatrix(cfg.species, this.rng));
    this.reseed();
    this._buildGrid();
  }

  setMatrix(matrix) {
    this.matrix = matrix instanceof Float32Array ? matrix : Float32Array.from(matrix);
    this.nSpecies = Math.round(Math.sqrt(this.matrix.length));
  }

  // Re-scatter particles; keeps the current matrix.
  reseed() {
    const { width, height } = this.cfg;
    for (let i = 0; i < this.n; i++) {
      this.px[i] = this.rng() * width;
      this.py[i] = this.rng() * height;
      this.vx[i] = 0;
      this.vy[i] = 0;
      this.species[i] = (this.rng() * this.nSpecies) | 0;
    }
  }

  resize(width, height) {
    // Rescale positions into the new world so nothing pops.
    const sx = width / this.cfg.width;
    const sy = height / this.cfg.height;
    for (let i = 0; i < this.n; i++) { this.px[i] *= sx; this.py[i] *= sy; }
    this.cfg.width = width;
    this.cfg.height = height;
    this._buildGrid();
  }

  _buildGrid() {
    const { width, height, rMax } = this.cfg;
    this.cols = Math.max(1, Math.floor(width / rMax));
    this.rows = Math.max(1, Math.floor(height / rMax));
    this.cellW = width / this.cols;
    this.cellH = height / this.rows;
    this.head = new Int32Array(this.cols * this.rows);
    this.next = new Int32Array(this.n);
  }

  _hashIntoGrid() {
    const { cols, rows, cellW, cellH, head, next, px, py, n } = this;
    head.fill(-1);
    for (let i = 0; i < n; i++) {
      let cx = Math.floor(px[i] / cellW); cx = ((cx % cols) + cols) % cols;
      let cy = Math.floor(py[i] / cellH); cy = ((cy % rows) + rows) % rows;
      const c = cx * rows + cy;
      next[i] = head[c];
      head[c] = i;
    }
  }

  step() {
    const { width, height, rMax, beta, forceScale, friction, dt } = this.cfg;
    const { px, py, vx, vy, species, matrix, nSpecies, cols, rows, cellW, cellH, head, next, n } = this;
    const hw = width * 0.5, hh = height * 0.5;
    const r2 = rMax * rMax;
    this._hashIntoGrid();

    for (let i = 0; i < n; i++) {
      const xi = px[i], yi = py[i], si = species[i];
      let ax = 0, ay = 0;
      let cx = Math.floor(xi / cellW); cx = ((cx % cols) + cols) % cols;
      let cy = Math.floor(yi / cellH); cy = ((cy % rows) + rows) % rows;

      for (let dx = -1; dx <= 1; dx++) {
        const ncx = (cx + dx + cols) % cols;
        for (let dy = -1; dy <= 1; dy++) {
          const ncy = (cy + dy + rows) % rows;
          let j = head[ncx * rows + ncy];
          while (j !== -1) {
            if (j !== i) {
              // minimum-image delta on the torus
              let ddx = px[j] - xi;
              let ddy = py[j] - yi;
              if (ddx > hw) ddx -= width; else if (ddx < -hw) ddx += width;
              if (ddy > hh) ddy -= height; else if (ddy < -hh) ddy += height;
              const d2 = ddx * ddx + ddy * ddy;
              if (d2 < r2 && d2 > 1e-12) {
                const dist = Math.sqrt(d2);
                const rn = dist / rMax;
                const a = matrix[si * nSpecies + species[j]];
                const f = forceCurve(rn, a, beta);
                const s = (f * forceScale * rMax) / dist;
                ax += ddx * s;
                ay += ddy * s;
              }
            }
            j = next[j];
          }
        }
      }
      vx[i] += ax * dt;
      vy[i] += ay * dt;
    }

    for (let i = 0; i < n; i++) {
      vx[i] *= friction;
      vy[i] *= friction;
      let x = px[i] + vx[i] * dt; x %= width; if (x < 0) x += width;
      let y = py[i] + vy[i] * dt; y %= height; if (y < 0) y += height;
      px[i] = x; py[i] = y;
    }
  }

  // -- live metrics for the vitality / boredom detector ----------------
  occupancy(binsX, binsY) {
    const occ = new Float32Array(binsX * binsY);
    const { px, py, n } = this;
    const { width, height } = this.cfg;
    for (let i = 0; i < n; i++) {
      let bx = Math.floor((px[i] / width) * binsX); if (bx >= binsX) bx = binsX - 1; if (bx < 0) bx = 0;
      let by = Math.floor((py[i] / height) * binsY); if (by >= binsY) by = binsY - 1; if (by < 0) by = 0;
      occ[bx * binsY + by] += 1;
    }
    return occ;
  }

  meanSpeed() {
    const { vx, vy, n } = this;
    let s = 0;
    for (let i = 0; i < n; i++) s += Math.hypot(vx[i], vy[i]);
    return s / n;
  }
}

const tanh = Math.tanh;

// Combine occupancy stats + speed + drift into clustering/motion/heterogeneity,
// mirroring the Python discovery.score so the browser and CLI agree on taste.
export function vitalityParts(occNow, occPrev, n, meanSpeed) {
  let sum = 0;
  for (let i = 0; i < occNow.length; i++) sum += occNow[i];
  const mean = sum / occNow.length;
  let varr = 0;
  for (let i = 0; i < occNow.length; i++) { const d = occNow[i] - mean; varr += d * d; }
  const std = Math.sqrt(varr / occNow.length);
  const clustering = mean > 0 ? tanh((std / mean) / 1.5) : 0;

  const motion = tanh(meanSpeed / 0.02);

  let drift = 0;
  if (occPrev) {
    for (let i = 0; i < occNow.length; i++) drift += Math.abs(occNow[i] - occPrev[i]);
    drift = drift / (2 * n);
  }
  const heterogeneity = tanh(drift / 0.3);

  const score = Math.cbrt(clustering * motion * heterogeneity);
  return { clustering, motion, heterogeneity, score };
}
