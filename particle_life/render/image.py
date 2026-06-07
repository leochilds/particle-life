"""Render simulation state to images.

Particles are drawn as soft additive glows on a dark field, which makes dense
clusters bloom and reveals structure the eye would otherwise miss. Colors are a
fixed, pleasant palette indexed by species.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

# A warm/cool palette that reads well on black (RGB, 0-255).
PALETTE = np.array(
    [
        [255, 89, 94],    # red
        [255, 202, 58],   # yellow
        [138, 201, 38],   # green
        [25, 130, 196],   # blue
        [106, 76, 147],   # purple
        [255, 146, 76],   # orange
        [82, 226, 220],   # cyan
        [240, 240, 240],  # white
    ],
    dtype=np.float32,
)


def _soft_dot(radius: int) -> np.ndarray:
    """A small Gaussian-ish brightness kernel in [0,1]."""
    span = np.arange(-radius, radius + 1)
    gx, gy = np.meshgrid(span, span)
    d2 = gx * gx + gy * gy
    k = np.exp(-d2 / (2.0 * (radius / 1.6) ** 2))
    k[d2 > radius * radius] = 0.0
    return k.astype(np.float32)


def render(pos: np.ndarray, species: np.ndarray, size: float,
           width: int = 800, glow: int = 3, gain: float = 1.0) -> Image.Image:
    """Additively splat each particle's colored glow onto a float canvas."""
    h = w = width
    canvas = np.zeros((h, w, 3), dtype=np.float32)
    kernel = _soft_dot(glow)
    r = glow

    px = np.clip((pos[:, 0] / size * (w - 1)).astype(int), 0, w - 1)
    py = np.clip((pos[:, 1] / size * (h - 1)).astype(int), 0, h - 1)
    colors = PALETTE[species % len(PALETTE)]

    for x, y, col in zip(px, py, colors):
        x0, x1 = x - r, x + r + 1
        y0, y1 = y - r, y + r + 1
        kx0 = max(0, -x0); ky0 = max(0, -y0)
        x0c, y0c = max(0, x0), max(0, y0)
        x1c, y1c = min(w, x1), min(h, y1)
        kx1 = kx0 + (x1c - x0c); ky1 = ky0 + (y1c - y0c)
        if x1c <= x0c or y1c <= y0c:
            continue
        sub = kernel[ky0:ky1, kx0:kx1, None] * col[None, None, :]
        canvas[y0c:y1c, x0c:x1c] += sub

    canvas *= gain
    # soft tone-map so bright cores don't just clip to flat white
    canvas = 255.0 * (1.0 - np.exp(-canvas / 255.0))
    return Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8), "RGB")
