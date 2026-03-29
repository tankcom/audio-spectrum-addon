from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StreamConfig:
    name: str
    url: str
    enabled: bool = True


@dataclass(frozen=True)
class MqttConfig:
    host: str = "core-mosquitto"
    port: int = 1883
    username: str = ""
    password: str = ""
    discovery_prefix: str = "homeassistant"
    base_topic: str = "audio_spectrum"


@dataclass(frozen=True)
class RestConfig:
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8099


@dataclass(frozen=True)
class AppConfig:
    streams: list[StreamConfig]
    sample_rate: int = 48000
    fft_size: int = 8192
    update_interval_ms: int = 250
    window_function: str = "hann"
    mqtt: MqttConfig = MqttConfig()
    rest: RestConfig = RestConfig()


def _as_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def load_config(options_file: str) -> AppConfig:
    path = Path(options_file)
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
    else:
        raw = {}

    streams_raw = raw.get("streams", [])
    streams: list[StreamConfig] = []
    for item in streams_raw:
        name = str(item.get("name", "")).strip()
        url = str(item.get("url", "")).strip()
        if not name or not url:
            continue
        streams.append(StreamConfig(name=name, url=url, enabled=_as_bool(item.get("enabled", True), True)))

    mqtt_raw = raw.get("mqtt", {})
    mqtt = MqttConfig(
        host=str(mqtt_raw.get("host", "core-mosquitto")),
        port=int(mqtt_raw.get("port", 1883)),
        username=str(mqtt_raw.get("username", "")),
        password=str(mqtt_raw.get("password", "")),
        discovery_prefix=str(mqtt_raw.get("discovery_prefix", "homeassistant")),
        base_topic=str(mqtt_raw.get("base_topic", "audio_spectrum")),
    )

    rest_raw = raw.get("rest", {})
    rest = RestConfig(
        enabled=_as_bool(rest_raw.get("enabled", True), True),
        host=str(rest_raw.get("host", "0.0.0.0")),
        port=int(rest_raw.get("port", 8099)),
    )

    fft_size = int(raw.get("fft_size", 8192))
    if fft_size not in {4096, 8192, 16384}:
        fft_size = 8192

    update_interval_ms = int(raw.get("update_interval_ms", 250))
    if update_interval_ms < 100:
        update_interval_ms = 100

    sample_rate = int(raw.get("sample_rate", 48000))
    if sample_rate < 8000 or sample_rate > 96000:
        sample_rate = 48000

    window_function = str(raw.get("window_function", "hann")).lower().strip()
    if window_function not in {"hann", "hamming", "blackman"}:
        window_function = "hann"

    enabled_streams = [s for s in streams if s.enabled]

    return AppConfig(
        streams=enabled_streams,
        sample_rate=sample_rate,
        fft_size=fft_size,
        update_interval_ms=update_interval_ms,
        window_function=window_function,
        mqtt=mqtt,
        rest=rest,
    )
