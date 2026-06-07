"""Command-line interface for Particle Life.

Examples
--------
  # Hunt for an interesting universe and save its matrix
  python3 -m particle_life discover --species 5 --trials 30 --out best.npy

  # Render a video from a saved matrix (or a fresh random one)
  python3 -m particle_life render --matrix best.npy --seconds 12 --out life.mp4

  # Render straight from a discovery search in one shot
  python3 -m particle_life render --discover --trials 30 --seconds 12 --out life.mp4
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from .core import Config, Simulation
from .core.discovery import discover
from .render import render
from .render.video import encode


def _frames(sim: Simulation, n_frames: int, width: int, glow: int,
            substeps: int, settle: int):
    for _ in range(settle):
        sim.step()
    for _ in range(n_frames):
        for _ in range(substeps):
            sim.step()
        yield render(sim.pos, sim.species, sim.cfg.size, width=width, glow=glow)


def cmd_discover(a: argparse.Namespace) -> int:
    cfg = Config(n_particles=a.particles, n_species=a.species)
    results = discover(cfg, trials=a.trials, seed=a.seed)
    print(f"{'rank':>4}  {'score':>6}  {'clust':>5}  {'motion':>6}  {'hetero':>6}  seed")
    for i, r in enumerate(results[:10]):
        print(f"{i:>4}  {r['score']:>6.3f}  {r['clustering']:>5.2f}  "
              f"{r['motion']:>6.2f}  {r['heterogeneity']:>6.2f}  {r['seed']}")
    best = results[0]
    np.save(a.out, best["matrix"])
    # stash the layout seed alongside so renders are reproducible
    Path(a.out).with_suffix(".seed").write_text(str(best["seed"]))
    print(f"\nsaved best matrix -> {a.out}  (layout seed {best['seed']})")
    return 0


def cmd_render(a: argparse.Namespace) -> int:
    matrix = None
    seed = a.seed
    if a.discover:
        cfg = Config(n_particles=a.particles, n_species=a.species)
        results = discover(cfg, trials=a.trials, seed=a.seed or 0)
        best = results[0]
        matrix, seed = best["matrix"], best["seed"]
        print(f"discovered universe: score={best['score']:.3f} seed={seed}")
    elif a.matrix:
        matrix = np.load(a.matrix)
        seed_file = Path(a.matrix).with_suffix(".seed")
        if seed is None and seed_file.exists():
            seed = int(seed_file.read_text())

    cfg = Config(n_particles=a.particles,
                 n_species=matrix.shape[0] if matrix is not None else a.species,
                 seed=seed)
    sim = Simulation(cfg, matrix=matrix)
    n_frames = int(a.seconds * a.fps)
    print(f"rendering {n_frames} frames ({a.seconds}s @ {a.fps}fps) ...")
    frames = _frames(sim, n_frames, a.width, a.glow, a.substeps, a.settle)
    out = encode(frames, a.out, fps=a.fps)
    print(f"wrote {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="particle_life", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="search for interesting universes")
    d.add_argument("--species", type=int, default=5)
    d.add_argument("--particles", type=int, default=800)
    d.add_argument("--trials", type=int, default=30)
    d.add_argument("--seed", type=int, default=0)
    d.add_argument("--out", type=str, default="best.npy")
    d.set_defaults(func=cmd_discover)

    r = sub.add_parser("render", help="render a universe to video")
    src = r.add_mutually_exclusive_group()
    src.add_argument("--matrix", type=str, help="path to a saved .npy matrix")
    src.add_argument("--discover", action="store_true", help="search, then render the winner")
    r.add_argument("--species", type=int, default=5)
    r.add_argument("--particles", type=int, default=1500)
    r.add_argument("--trials", type=int, default=30)
    r.add_argument("--seconds", type=float, default=12.0)
    r.add_argument("--fps", type=int, default=30)
    r.add_argument("--substeps", type=int, default=1, help="sim steps per rendered frame")
    r.add_argument("--settle", type=int, default=200, help="warmup steps before recording")
    r.add_argument("--width", type=int, default=800)
    r.add_argument("--glow", type=int, default=4)
    r.add_argument("--seed", type=int, default=None)
    r.add_argument("--out", type=str, default="life.mp4")
    r.set_defaults(func=cmd_render)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
