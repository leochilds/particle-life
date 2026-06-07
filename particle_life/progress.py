"""A tiny dependency-free progress bar that updates a single terminal line.

Writes to stderr so it never pollutes piped stdout, and degrades gracefully when
output isn't a TTY (it prints occasional plain lines instead of redrawing).
"""

from __future__ import annotations

import sys
import time
from typing import TextIO


def _fmt_time(seconds: float) -> str:
    if seconds < 0 or seconds != seconds:  # negative or NaN
        return "--:--"
    m, s = divmod(int(seconds), 60)
    return f"{m:d}:{s:02d}"


class Progress:
    """Track progress over `total` steps and render a live status line.

    Usage:
        p = Progress(total, label="rendering")
        for ... :
            ...
            p.update(suffix="extra info")
        p.done()
    """

    def __init__(self, total: int, label: str = "", width: int = 24,
                 stream: TextIO | None = None, min_interval: float = 0.1):
        self.total = max(1, total)
        self.label = label
        self.width = width
        self.stream = stream or sys.stderr
        self.min_interval = min_interval
        self.n = 0
        self._start = time.perf_counter()
        self._last_draw = 0.0
        self._tty = getattr(self.stream, "isatty", lambda: False)()

    def update(self, step: int = 1, suffix: str = "") -> None:
        self.n = min(self.total, self.n + step)
        now = time.perf_counter()
        # throttle redraws, but always draw the final step
        if self.n < self.total and (now - self._last_draw) < self.min_interval:
            return
        self._last_draw = now
        self._draw(now, suffix)

    def _draw(self, now: float, suffix: str) -> None:
        frac = self.n / self.total
        elapsed = now - self._start
        rate = self.n / elapsed if elapsed > 0 else 0.0
        eta = (self.total - self.n) / rate if rate > 0 else float("nan")

        filled = int(self.width * frac)
        bar = "█" * filled + "░" * (self.width - filled)
        head = f"{self.label} " if self.label else ""
        line = (f"{head}[{bar}] {self.n}/{self.total} "
                f"{frac * 100:5.1f}%  {rate:4.1f}/s  "
                f"ETA {_fmt_time(eta)}")
        if suffix:
            line += f"  {suffix}"

        if self._tty:
            self.stream.write("\r\033[K" + line)
        else:
            # non-interactive: only emit periodic plain lines to avoid spam
            self.stream.write(line + "\n")
        self.stream.flush()

    def done(self, suffix: str = "") -> None:
        self.n = self.total
        elapsed = time.perf_counter() - self._start
        head = f"{self.label} " if self.label else ""
        line = f"{head}done — {self.total} in {_fmt_time(elapsed)}"
        if suffix:
            line += f"  {suffix}"
        if self._tty:
            self.stream.write("\r\033[K" + line + "\n")
        else:
            self.stream.write(line + "\n")
        self.stream.flush()
