from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import time
from pathlib import Path

import numpy as np
from aiohttp import web

from .constants import DEFAULT_WATERFALL_HISTORY, TARGET_FREQUENCIES_HZ
from .mqtt_publisher import MqttPublisher, MqttPublisherConfig
from .settings import AppConfig, StreamConfig, load_config
from .spectrum import SpectrumAnalyzer
from .stream_worker import StreamIdentity, StreamWorker
from .waterfall import WaterfallStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger(__name__)
RUNTIME_STREAMS_FILE = Path("/config/audio_spectrum_streams.json")


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "stream"


def _normalize_streams(raw_streams: list[dict[str, object]]) -> list[StreamConfig]:
    normalized: list[StreamConfig] = []
    for item in raw_streams:
        name = str(item.get("name", "")).strip()
        url = str(item.get("url", "")).strip()
        enabled_raw = item.get("enabled", True)
        if isinstance(enabled_raw, str):
            enabled = enabled_raw.strip().lower() in {"1", "true", "yes", "on"}
        else:
            enabled = bool(enabled_raw)
        if not name or not url:
            continue
        normalized.append(StreamConfig(name=name, url=url, enabled=enabled))
    return normalized


def _serialize_streams(streams: list[StreamConfig]) -> list[dict[str, object]]:
    return [{"name": s.name, "url": s.url, "enabled": s.enabled} for s in streams]


def _load_runtime_streams(default_streams: list[StreamConfig]) -> list[StreamConfig]:
    if not RUNTIME_STREAMS_FILE.is_file():
        return default_streams

    try:
        raw = json.loads(RUNTIME_STREAMS_FILE.read_text(encoding="utf-8"))
        parsed = raw.get("streams", []) if isinstance(raw, dict) else []
        runtime_streams = _normalize_streams(parsed)
        if runtime_streams:
            return [stream for stream in runtime_streams if stream.enabled]
    except Exception as exc:
        LOGGER.warning("failed to load runtime streams file: %s", exc)
    return default_streams


def _save_runtime_streams(streams: list[StreamConfig]) -> None:
    RUNTIME_STREAMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"streams": _serialize_streams(streams)}
    RUNTIME_STREAMS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _build_unique_identities(streams: list[StreamConfig]) -> list[StreamIdentity]:
    identities: list[StreamIdentity] = []
    used_slugs: dict[str, int] = {}
    for stream in streams:
        base_slug = slugify(stream.name)
        count = used_slugs.get(base_slug, 0)
        used_slugs[base_slug] = count + 1
        slug = base_slug if count == 0 else f"{base_slug}-{count + 1}"
        identities.append(StreamIdentity(name=stream.name, slug=slug, url=stream.url))
    return identities


class SharedState:
    def __init__(self, streams: list[StreamConfig]) -> None:
        self._lock = asyncio.Lock()
        self._streams = streams
        self._latest: dict[str, dict[str, object]] = {}

    async def set_streams(self, streams: list[StreamConfig]) -> None:
        async with self._lock:
            self._streams = streams

    async def update_live(self, identity: StreamIdentity, ts: float, spectrum: dict[str, dict[str, float]]) -> None:
        async with self._lock:
            self._latest[identity.slug] = {
                "name": identity.name,
                "slug": identity.slug,
                "timestamp": ts,
                "spectrum": spectrum,
            }

    async def live_payload(self) -> dict[str, object]:
        async with self._lock:
            return {
                "streams": _serialize_streams(self._streams),
                "live": self._latest,
            }

    async def config_payload(self) -> dict[str, object]:
        async with self._lock:
            return {"streams": _serialize_streams(self._streams)}


async def start_rest_server(
    store: WaterfallStore,
    state: SharedState,
    host: str,
    port: int,
    request_reconfigure: asyncio.Queue[list[StreamConfig]],
) -> web.AppRunner:
    app = web.Application()
    static_dir = Path(__file__).resolve().parent / "web"

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def waterfall(_: web.Request) -> web.Response:
        payload = await store.snapshot()
        return web.json_response(payload)

    async def live(_: web.Request) -> web.Response:
        return web.json_response(await state.live_payload())

    async def get_config(_: web.Request) -> web.Response:
        return web.json_response(await state.config_payload())

    async def set_streams(request: web.Request) -> web.Response:
        payload = await request.json()
        stream_items = payload.get("streams", []) if isinstance(payload, dict) else []
        streams = _normalize_streams(stream_items)

        _save_runtime_streams(streams)

        while not request_reconfigure.empty():
            try:
                _ = request_reconfigure.get_nowait()
            except asyncio.QueueEmpty:
                break
        await request_reconfigure.put([stream for stream in streams if stream.enabled])

        await state.set_streams([stream for stream in streams if stream.enabled])
        return web.json_response({"ok": True, "streams": _serialize_streams(streams)})

    async def index(_: web.Request) -> web.Response:
        return web.FileResponse(static_dir / "index.html")

    app.add_routes(
        [
            web.get("/", index),
            web.get("/health", health),
            web.get("/waterfall", waterfall),
            web.get("/api/waterfall", waterfall),
            web.get("/api/live", live),
            web.get("/api/config", get_config),
            web.post("/api/config/streams", set_streams),
        ]
    )
    app.router.add_static("/static", static_dir)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    LOGGER.info("REST endpoint listening on %s:%s", host, port)
    return runner


async def run(config: AppConfig) -> None:
    configured_streams = _load_runtime_streams(config.streams)
    active_streams = [stream for stream in configured_streams if stream.enabled]

    analyzer = SpectrumAnalyzer(
        sample_rate=config.sample_rate,
        fft_size=config.fft_size,
        window_function=config.window_function,
    )

    publisher = MqttPublisher(
        MqttPublisherConfig(
            host=config.mqtt.host,
            port=config.mqtt.port,
            username=config.mqtt.username,
            password=config.mqtt.password,
            discovery_prefix=config.mqtt.discovery_prefix,
            base_topic=config.mqtt.base_topic,
        )
    )

    store = WaterfallStore(max_frames=DEFAULT_WATERFALL_HISTORY)
    state = SharedState(active_streams)
    rest_runner: web.AppRunner | None = None
    request_reconfigure: asyncio.Queue[list[StreamConfig]] = asyncio.Queue(maxsize=1)

    identities: list[StreamIdentity] = []
    workers: dict[str, StreamWorker] = {}
    rolling_buffers: dict[str, np.ndarray] = {}

    async def stop_all_workers() -> None:
        for identity in identities:
            publisher.publish_availability(identity, online=False)
        for worker in workers.values():
            await worker.stop()

    async def configure_workers(streams: list[StreamConfig]) -> None:
        nonlocal identities, workers, rolling_buffers
        await stop_all_workers()

        identities = _build_unique_identities(streams)
        workers = {}
        rolling_buffers = {}

        for identity in identities:
            worker = StreamWorker(identity=identity, sample_rate=config.sample_rate)
            workers[identity.slug] = worker
            rolling_buffers[identity.slug] = np.empty(0, dtype=np.float32)
            publisher.publish_discovery(identity)
            publisher.publish_availability(identity, online=True)
            worker.start()

        await state.set_streams(streams)
        LOGGER.info("active streams reconfigured: %d", len(identities))

    try:
        publisher.connect()
        await configure_workers(active_streams)

        if config.rest.enabled:
            rest_runner = await start_rest_server(
                store,
                state,
                config.rest.host,
                config.rest.port,
                request_reconfigure,
            )

        tick_seconds = config.update_interval_ms / 1000.0
        while True:
            pending_streams: list[StreamConfig] | None = None
            while True:
                try:
                    pending_streams = request_reconfigure.get_nowait()
                except asyncio.QueueEmpty:
                    break
            if pending_streams is not None:
                await configure_workers(pending_streams)

            tick_start = time.time()
            for identity in identities:
                worker = workers.get(identity.slug)
                if worker is None:
                    continue
                new_samples = worker.drain_samples()
                if new_samples.size == 0:
                    continue

                joined = np.concatenate([rolling_buffers[identity.slug], new_samples])
                if joined.size > config.fft_size:
                    joined = joined[-config.fft_size :]
                rolling_buffers[identity.slug] = joined

                spectrum = analyzer.analyze(joined, TARGET_FREQUENCIES_HZ)
                if not spectrum:
                    continue

                publisher.publish_state(identity, spectrum)
                await store.add(identity.slug, ts=tick_start, values=spectrum)
                await state.update_live(identity, tick_start, spectrum)

            elapsed = time.time() - tick_start
            await asyncio.sleep(max(0.0, tick_seconds - elapsed))
    finally:
        await stop_all_workers()

        if rest_runner is not None:
            await rest_runner.cleanup()

        publisher.stop()


def main(argv: list[str]) -> int:
    options_file = argv[1] if len(argv) > 1 else "/data/options.json"
    try:
        config = load_config(options_file)
    except Exception as exc:
        LOGGER.error("configuration error: %s", exc)
        return 2

    LOGGER.info(
        "starting with %d configured streams, sample_rate=%d, fft_size=%d, interval=%dms",
        len(config.streams),
        config.sample_rate,
        config.fft_size,
        config.update_interval_ms,
    )

    try:
        asyncio.run(run(config))
    except KeyboardInterrupt:
        LOGGER.info("shutdown requested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
