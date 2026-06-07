"""Tests for the simulation core.

These check the invariants that matter for a physics-y sandbox: state stays
finite and bounded, the world really does wrap, the force curve has the right
shape, and the neighbor search agrees with a brute-force reference.
"""

import numpy as np
import pytest

from particle_life.core import Config, Simulation, make_matrix
from particle_life.core.engine import _force_curve


def test_state_stays_finite_and_bounded():
    cfg = Config(n_particles=400, n_species=4, seed=1)
    sim = Simulation(cfg)
    sim.run(200)
    assert np.isfinite(sim.pos).all()
    assert np.isfinite(sim.vel).all()
    assert (sim.pos >= 0).all() and (sim.pos <= cfg.size).all()


def test_reproducible_with_seed():
    a = Simulation(Config(n_particles=300, seed=123))
    b = Simulation(Config(n_particles=300, seed=123))
    a.run(50); b.run(50)
    assert np.allclose(a.pos, b.pos)
    assert np.allclose(a.vel, b.vel)


def test_force_curve_shape():
    beta = 0.3
    r = np.linspace(0, 1, 200)
    # all-attractive coefficients
    a = np.ones_like(r)
    f = _force_curve(r, a, beta)
    # hard core: repulsive (negative) near r=0, zero exactly at r=beta
    assert f[0] < 0
    assert abs(_force_curve(np.array([beta]), np.array([1.0]), beta)[0]) < 1e-6
    # vanishes at the interaction edge
    assert abs(f[-1]) < 1e-6
    # peak attraction sits in the outer band
    assert f.max() > 0


def test_force_sign_follows_matrix():
    beta = 0.3
    r = np.array([0.65])  # near the outer peak
    pos = _force_curve(r, np.array([1.0]), beta)[0]
    neg = _force_curve(r, np.array([-1.0]), beta)[0]
    assert pos > 0 and neg < 0
    assert np.isclose(pos, -neg)


def test_neighbor_search_matches_bruteforce():
    """The grid search must find every pair within r_max that brute force does."""
    cfg = Config(n_particles=250, n_species=3, r_max=0.12, seed=5)
    sim = Simulation(cfg)
    sim.run(20)  # let them spread into multiple cells

    i, j = sim._neighbor_pairs()
    m = i != j
    i, j = i[m], j[m]
    d = sim.pos[j] - sim.pos[i]
    d -= cfg.size * np.round(d / cfg.size)
    dist = np.sqrt((d * d).sum(1))
    grid_pairs = {tuple(sorted(p)) for p in zip(i[dist < cfg.r_max], j[dist < cfg.r_max])}

    # brute force reference with the same minimum-image metric
    P = sim.pos
    diff = P[:, None, :] - P[None, :, :]
    diff -= cfg.size * np.round(diff / cfg.size)
    D = np.sqrt((diff ** 2).sum(-1))
    ii, jj = np.where((D < cfg.r_max) & (np.arange(len(P))[:, None] != np.arange(len(P))[None, :]))
    brute_pairs = {tuple(sorted(p)) for p in zip(ii, jj)}

    assert grid_pairs == brute_pairs


def test_matrix_is_asymmetric_in_general():
    rng = np.random.default_rng(0)
    m = make_matrix(5, rng)
    assert not np.allclose(m, m.T)
    assert m.min() >= -1 and m.max() <= 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
