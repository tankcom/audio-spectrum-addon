from __future__ import annotations

import asyncio
import logging
import re
import sys
import time
from typing import Any

import numpy as np
from aiohttp import web

from .constants import TARGET_FREQUENCIES_HZ
from .mqtt_publisher import MqttPublisher, MqttPublisherConfig
from .settings import AppConfig, load_config
from .spectrum import SpectrumAnalyzer
from .stream_worker import StreamIdentity, StreamWorker
from .waterfall import WaterfallStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger(__name__)


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "stream"


async def start_rest_server(store: WaterfallStore, host: str, port: int) -> web.AppRunner:
    app = web.Application()

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def waterfall(_: web.Request) -> web.Response:
        payload = await store.snapshot()
        return web.json_response(payload)

    app.add_routes(
        [
            web.get("/health", health),
            web.get("/waterfall", waterfall),
        ]
    )

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    LOGGER.info("REST endpoint listening on %s:%s", host, port)
    return runner


async def run(config: AppConfig) -> None:
    identities = [
        StreamIdentity(name=s.name, slug=slugify(s.name), url=s.url)
        for s in config.streams
    ]

    workers = [StreamWorker(identity=i, sample_rate=config.sample_rate) for i in identities]
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

    store = WaterfallStore()
    rest_runner: web.AppRunner | None = None

    rolling_buffers: dict[str, np.ndarray] = {
        identity.slug: np.empty(0, dtype=np.float32) for identity in identities
    }

    try:
        publisher.connect()
        for identity in identities:
            publisher.publish_discovery(identity)
            publisher.publish_availability(identity, online=True)

        for worker in workers:
            worker.start()

        if config.rest.enabled:
            rest_runner = await start_rest_server(store, config.rest.host, config.rest.port)

        tick_seconds = config.update_interval_ms / 1000.0
        while True:
            tick_start = time.time()
            for identity, worker in zip(identities, workers):
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

            elapsed = time.time() - tick_start
            await asyncio.sleep(max(0.0, tick_seconds - elapsed))
    finally:
        for identity in identities:
            publisher.publish_availability(identity, online=False)

        for worker in workers:
            await worker.stop()

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
        "starting with %d streams, sample_rate=%d, fft_size=%d, interval=%dms",
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
