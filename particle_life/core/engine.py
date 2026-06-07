"""Particle Life simulation engine.

A minimal model of emergent artificial life. Particles belong to a small number
of "species" (colors). Every pair of species has an interaction coefficient in
[-1, 1]: positive means attraction, negative means repulsion. The matrix is
*asymmetric* on purpose -- A may chase B while B flees A -- which is what makes
the dynamics so lifelike.

Forces are short range. Each particle only feels neighbors within `r_max`, so we
use a uniform spatial-hash grid to find neighbors in ~O(N) instead of O(N^2).
The world is a torus (wraps at the edges) so there are no walls to pile up on.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Config:
    n_particles: int = 1500
    n_species: int = 5
    size: float = 1.0            # world is size x size, wraps around (torus)
    r_max: float = 0.10          # interaction radius (fraction of world)
    beta: float = 0.30           # core radius fraction: closer than beta*r_max -> always repel
    force_scale: float = 4.0     # global strength of interaction forces
    friction: float = 0.85       # velocity retained per step (0..1); lower = more damping
    dt: float = 0.012            # integration timestep
    seed: int | None = None


def make_matrix(n_species: int, rng: np.random.Generator) -> np.ndarray:
    """Random asymmetric interaction matrix with values in [-1, 1]."""
    return rng.uniform(-1.0, 1.0, size=(n_species, n_species)).astype(np.float32)


def _force_curve(r: np.ndarray, a: np.ndarray, beta: float) -> np.ndarray:
    """Piecewise force as a function of normalized distance r in [0, 1].

    r < beta            : strong universal repulsion (a hard core; rises to -1 at r=0)
    beta <= r <= 1      : a triangular attraction/repulsion of signed strength `a`,
                          peaking at the midpoint and fading to 0 at both ends.

    This is the classic Clusters/Particle-Life curve. Returns force magnitude;
    positive = attractive (pull together), negative = repulsive (push apart).
    """
    out = np.zeros_like(r)
    core = r < beta
    out[core] = r[core] / beta - 1.0  # -1 at r=0 up to 0 at r=beta
    outer = ~core
    # triangular bump: 0 at beta, peak (=a) at (1+beta)/2, 0 at 1
    out[outer] = a[outer] * (1.0 - np.abs(2.0 * r[outer] - 1.0 - beta) / (1.0 - beta))
    return out


class Simulation:
    """Holds state and steps the world forward."""

    def __init__(self, cfg: Config, matrix: np.ndarray | None = None):
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg.seed)
        self.matrix = make_matrix(cfg.n_species, self.rng) if matrix is None else matrix.astype(np.float32)

        n = cfg.n_particles
        self.pos = self.rng.random((n, 2), dtype=np.float32) * cfg.size
        self.vel = np.zeros((n, 2), dtype=np.float32)
        self.species = self.rng.integers(0, cfg.n_species, size=n).astype(np.int32)

        # spatial-hash grid sizing
        self._ncell = max(1, int(cfg.size / cfg.r_max))
        self._cell = cfg.size / self._ncell

    # -- spatial hashing -------------------------------------------------
    def _cell_index(self, pos: np.ndarray) -> np.ndarray:
        c = np.floor(pos / self._cell).astype(np.int32) % self._ncell
        return c[:, 0] * self._ncell + c[:, 1]

    def _neighbor_pairs(self) -> tuple[np.ndarray, np.ndarray]:
        """Return index arrays (i, j) of particle pairs in adjacent cells.

        We bucket particles into cells, then for each of the 9 cell offsets pair
        every particle with the occupants of its neighbor cell. This produces a
        candidate set; the distance filter happens in step().
        """
        nc = self._ncell
        cell = self._cell_index(self.pos)
        order = np.argsort(cell, kind="stable")
        sorted_cell = cell[order]
        # start index of each cell id within `order`
        starts = np.searchsorted(sorted_cell, np.arange(nc * nc))
        ends = np.searchsorted(sorted_cell, np.arange(nc * nc), side="right")

        cx = np.floor(self.pos[:, 0] / self._cell).astype(np.int32) % nc
        cy = np.floor(self.pos[:, 1] / self._cell).astype(np.int32) % nc

        i_list, j_list = [], []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                ncx = (cx + dx) % nc
                ncy = (cy + dy) % nc
                ncell = ncx * nc + ncy
                s = starts[ncell]
                e = ends[ncell]
                counts = e - s
                if counts.sum() == 0:
                    continue
                # for every particle i, gather all j in its neighbor cell
                rep_i = np.repeat(np.arange(self.cfg.n_particles), counts)
                # build the concatenated j indices
                segs = [order[s[k]:e[k]] for k in range(len(s)) if counts[k] > 0]
                if not segs:
                    continue
                rep_j = np.concatenate(segs)
                i_list.append(rep_i)
                j_list.append(rep_j)
        if not i_list:
            return np.empty(0, np.int64), np.empty(0, np.int64)
        return np.concatenate(i_list), np.concatenate(j_list)

    # -- integration -----------------------------------------------------
    def step(self) -> None:
        cfg = self.cfg
        i, j = self._neighbor_pairs()
        if i.size:
            mask = i != j
            i, j = i[mask], j[mask]

            d = self.pos[j] - self.pos[i]
            # minimum-image convention for the torus
            d -= cfg.size * np.round(d / cfg.size)
            dist = np.sqrt((d * d).sum(axis=1))

            within = dist < cfg.r_max
            i, j, d, dist = i[within], j[within], d[within], dist[within]

            rn = dist / cfg.r_max
            a = self.matrix[self.species[i], self.species[j]]
            f = _force_curve(rn, a, cfg.beta)

            safe = dist > 1e-6
            dir_ = np.zeros_like(d)
            dir_[safe] = d[safe] / dist[safe, None]
            contrib = dir_ * f[:, None] * cfg.force_scale * cfg.r_max

            acc = np.zeros_like(self.vel)
            np.add.at(acc, i, contrib)
            self.vel += acc * cfg.dt

        self.vel *= cfg.friction
        self.pos = (self.pos + self.vel * cfg.dt) % cfg.size

    def run(self, n_steps: int) -> None:
        for _ in range(n_steps):
            self.step()
