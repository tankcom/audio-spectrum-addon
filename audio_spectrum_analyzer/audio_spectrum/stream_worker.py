from __future__ import annotations

import asyncio
import logging
import shlex
from dataclasses import dataclass

import numpy as np

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class StreamIdentity:
    name: str
    slug: str
    url: str


class StreamWorker:
    def __init__(self, identity: StreamIdentity, sample_rate: int, chunk_size: int = 4096) -> None:
        self.identity = identity
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self._queue: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=32)
        self._task: asyncio.Task[None] | None = None
        self._running = False

    def start(self) -> None:
        if self._task is None:
            self._running = True
            self._task = asyncio.create_task(self._run(), name=f"stream-{self.identity.slug}")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def drain_samples(self) -> np.ndarray:
        if self._queue.empty():
            return np.empty(0, dtype=np.float32)

        chunks: list[np.ndarray] = []
        while True:
            try:
                chunks.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        if not chunks:
            return np.empty(0, dtype=np.float32)

        return np.concatenate(chunks)

    async def _run(self) -> None:
        backoff_seconds = 1.0
        while self._running:
            cmd = (
                "ffmpeg -hide_banner -loglevel error "
                f"-i {shlex.quote(self.identity.url)} -vn -ac 1 "
                f"-ar {self.sample_rate} -f s16le -acodec pcm_s16le pipe:1"
            )
            LOGGER.info("starting ffmpeg for stream %s", self.identity.name)
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                assert process.stdout is not None
                while self._running:
                    raw = await process.stdout.read(self.chunk_size)
                    if not raw:
                        raise RuntimeError("ffmpeg stdout ended")

                    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                    await self._push_chunk(pcm)

                break
            except Exception as exc:
                LOGGER.warning(
                    "stream %s disconnected: %s; reconnecting in %.1fs",
                    self.identity.name,
                    exc,
                    backoff_seconds,
                )
            finally:
                if process.returncode is None:
                    process.kill()
                await process.wait()

            await asyncio.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2.0, 15.0)

    async def _push_chunk(self, chunk: np.ndarray) -> None:
        if self._queue.full():
            try:
                _ = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        await self._queue.put(chunk)
