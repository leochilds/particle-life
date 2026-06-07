"""Search for interesting universes.

Most random interaction matrices produce one of two boring outcomes: a uniform
gas (nothing clumps) or a dead collapse (everything freezes into one blob). The
interesting universes live in between -- structured, moving, persistently
changing. We quantify that with a cheap "interestingness" score and sample many
matrices to find good ones.

The score rewards three things measured after the world has settled:

  * clustering   -- particles are non-uniformly distributed (structure exists)
  * motion       -- the system keeps moving (it isn't frozen)
  * heterogeneity-- different regions look different (not one uniform texture)

Each is normalized to ~[0,1]; the product favors universes good at all three.
"""

from __future__ import annotations

import numpy as np

from .engine import Config, Simulation, make_matrix


def _occupancy(pos: np.ndarray, size: float, bins: int) -> np.ndarray:
    h, _, _ = np.histogram2d(pos[:, 0], pos[:, 1], bins=bins, range=[[0, size], [0, size]])
    return h


def score(sim: Simulation, settle: int = 250, measure: int = 60) -> dict:
    """Run the sim and return a dict with sub-scores and a combined value."""
    sim.run(settle)

    bins = 32
    occ0 = _occupancy(sim.pos, sim.cfg.size, bins)
    speeds = []
    drift = np.zeros((bins, bins))
    for _ in range(measure):
        sim.step()
        speeds.append(float(np.sqrt((sim.vel ** 2).sum(1)).mean()))
    occ1 = _occupancy(sim.pos, sim.cfg.size, bins)

    # clustering: coefficient of variation of cell occupancy (0 = uniform)
    mean = occ1.mean()
    clustering = float(occ1.std() / mean) if mean > 0 else 0.0
    clustering = np.tanh(clustering / 1.5)  # squash to ~[0,1]

    # motion: mean speed over the measurement window, squashed
    motion = float(np.tanh(np.mean(speeds) / 0.02))

    # heterogeneity: how much the occupancy map *changed* during measurement
    drift = np.abs(occ1 - occ0).sum() / (2 * sim.cfg.n_particles)
    heterogeneity = float(np.tanh(drift / 0.3))

    combined = (clustering * motion * heterogeneity) ** (1 / 3)
    return {
        "clustering": clustering,
        "motion": motion,
        "heterogeneity": heterogeneity,
        "score": combined,
    }


def discover(cfg: Config, trials: int = 40, seed: int = 0, on_trial=None) -> list[dict]:
    """Sample `trials` random matrices, score each, return sorted best-first.

    `on_trial(index, total, result, best_so_far)` is called after every trial,
    letting callers report progress without this module knowing about the UI.
    """
    rng = np.random.default_rng(seed)
    results = []
    best = None
    for t in range(trials):
        m = make_matrix(cfg.n_species, rng)
        # fresh sim with its own layout seed but the candidate matrix
        c = Config(**{**cfg.__dict__, "seed": int(rng.integers(1 << 30))})
        sim = Simulation(c, matrix=m)
        s = score(sim)
        s["matrix"] = m
        s["seed"] = c.seed
        results.append(s)
        if best is None or s["score"] > best["score"]:
            best = s
        if on_trial is not None:
            on_trial(t + 1, trials, s, best)
    results.sort(key=lambda d: d["score"], reverse=True)
    return results
