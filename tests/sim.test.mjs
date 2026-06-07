// Tests for the browser engine (docs/sim.js), run under Node's built-in test
// runner:  node --test tests/    (or `npm test`).
//
// These mirror the Python tests/test_engine.py invariants and add coverage for
// the bits unique to the web build: the pointer impulse and the vitality score.

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { Simulation, randomMatrix, mulberry32, vitalityParts } from '../docs/sim.js';

test('state stays finite and in-bounds', () => {
  const sim = new Simulation({ n: 400, species: 4, seed: 1 });
  for (let i = 0; i < 200; i++) sim.step();
  for (let i = 0; i < sim.n; i++) {
    assert.ok(Number.isFinite(sim.px[i]) && Number.isFinite(sim.py[i]));
    assert.ok(Number.isFinite(sim.vx[i]) && Number.isFinite(sim.vy[i]));
    assert.ok(sim.px[i] >= 0 && sim.px[i] <= sim.cfg.width);
    assert.ok(sim.py[i] >= 0 && sim.py[i] <= sim.cfg.height);
  }
});

test('reproducible from the same seed', () => {
  const a = new Simulation({ n: 300, species: 5, seed: 123 });
  const b = new Simulation({ n: 300, species: 5, seed: 123 });
  for (let i = 0; i < 60; i++) { a.step(); b.step(); }
  for (let i = 0; i < a.n; i++) {
    assert.equal(a.px[i], b.px[i]);
    assert.equal(a.vy[i], b.vy[i]);
  }
});

test('random matrix has the right shape and range', () => {
  const rng = mulberry32(7);
  const m = randomMatrix(5, rng);
  assert.equal(m.length, 25);
  for (const v of m) assert.ok(v >= -1 && v <= 1);
});

test('attractive impulse pulls particles toward the point', () => {
  const sim = new Simulation({ n: 500, species: 3, seed: 2 });
  const cx = sim.cfg.width / 2, cy = sim.cfg.height / 2;
  const meanDist = () => {
    let s = 0;
    for (let i = 0; i < sim.n; i++) s += Math.hypot(sim.px[i] - cx, sim.py[i] - cy);
    return s / sim.n;
  };
  const before = meanDist();
  for (let i = 0; i < 40; i++) {
    sim.applyImpulse(cx, cy, 0.5, 0.08, -1);   // sign -1 == attract
    sim.step();
  }
  assert.ok(meanDist() < before, 'particles should be closer to the attractor');
});

test('vitality scores concentrated higher than uniform', () => {
  const bins = 16, n = 256;
  const uniform = new Float32Array(bins * bins).fill(n / (bins * bins));
  const clumped = new Float32Array(bins * bins);
  clumped[0] = n;   // everything in one cell
  const u = vitalityParts(uniform, uniform, n, 0.03);
  const c = vitalityParts(clumped, uniform, n, 0.03);
  assert.ok(c.clustering > u.clustering);
  assert.ok(u.clustering < 0.05, 'uniform occupancy should read as unclustered');
});

test('frozen system reads as low motion', () => {
  // zero velocities -> meanSpeed 0 -> motion 0 -> score 0
  const occ = new Float32Array(64).fill(4);
  const parts = vitalityParts(occ, occ, 256, 0);
  assert.equal(parts.motion, 0);
  assert.equal(parts.score, 0);
});
