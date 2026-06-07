"""Encode a sequence of frames to MP4/GIF via ffmpeg.

We pipe raw RGB frames straight into ffmpeg's stdin so nothing touches disk
until the final video. This keeps long renders cheap on I/O.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Iterator

import numpy as np
from PIL import Image


def _ffmpeg() -> str:
    """Locate an ffmpeg binary.

    Prefer one on PATH; otherwise fall back to the self-contained binary that
    ships with the `imageio-ffmpeg` wheel, so a fresh `pip install` works even on
    a host with no system ffmpeg.
    """
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    raise RuntimeError(
        "ffmpeg not found. Install it via your package manager, or "
        "`pip install imageio-ffmpeg` to use a bundled copy."
    )


def encode(frames: Iterator[Image.Image], out_path: str | Path, fps: int = 30) -> Path:
    """Stream PIL frames into ffmpeg. Output format inferred from extension."""
    out_path = Path(out_path)
    first = next(frames)
    w, h = first.size

    args = [
        _ffmpeg(), "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{w}x{h}", "-r", str(fps),
        "-i", "pipe:0",
    ]
    if out_path.suffix.lower() == ".gif":
        # palette-based GIF for decent quality
        args += ["-vf", "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse", str(out_path)]
    else:
        args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(out_path)]

    proc = subprocess.Popen(args, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert proc.stdin is not None
    proc.stdin.write(np.asarray(first, dtype=np.uint8).tobytes())
    for frame in frames:
        proc.stdin.write(np.asarray(frame, dtype=np.uint8).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg encoding failed")
    return out_path
