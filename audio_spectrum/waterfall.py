from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass
class WaterfallFrame:
    ts: float
    values: list[float]


class WaterfallStore:
    def __init__(self, max_frames: int = 240) -> None:
        self._max_frames = max_frames
        self._frames: dict[str, deque[WaterfallFrame]] = {}
        self._scales: dict[str, dict[str, int]] = {}
        self._lock = asyncio.Lock()

    async def add(self, stream_slug: str, ts: float, values: list[float], step_hz: int, max_hz: int) -> None:
        async with self._lock:
            if stream_slug not in self._frames:
                self._frames[stream_slug] = deque(maxlen=self._max_frames)
            self._scales[stream_slug] = {"step_hz": step_hz, "max_hz": max_hz}
            self._frames[stream_slug].append(WaterfallFrame(ts=ts, values=values))

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock:
            return {
                slug: {
                    "step_hz": self._scales.get(slug, {}).get("step_hz", 10),
                    "max_hz": self._scales.get(slug, {}).get("max_hz", 20000),
                    "frames": [{"ts": frame.ts, "values": frame.values} for frame in frames],
                }
                for slug, frames in self._frames.items()
            }
