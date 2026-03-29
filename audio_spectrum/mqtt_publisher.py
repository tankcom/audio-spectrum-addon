from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import paho.mqtt.client as mqtt

from .constants import TARGET_FREQUENCIES_HZ
from .stream_worker import StreamIdentity

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MqttPublisherConfig:
    host: str
    port: int
    username: str
    password: str
    discovery_prefix: str
    base_topic: str


class MqttPublisher:
    def __init__(self, config: MqttPublisherConfig) -> None:
        self.config = config
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if config.username:
            self.client.username_pw_set(config.username, config.password)

    def connect(self) -> None:
        self.client.connect(self.config.host, self.config.port, keepalive=60)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def publish_discovery(self, stream: StreamIdentity) -> None:
        device = {
            "identifiers": [f"audio-spectrum-{stream.slug}"],
            "name": f"Audio Spectrum {stream.name}",
            "manufacturer": "Custom",
            "model": "RTSP/RTMP Spectrum Add-on",
        }

        availability_topic = self._availability_topic(stream)
        state_topic = self._state_topic(stream)

        for freq in TARGET_FREQUENCIES_HZ:
            object_id = f"audio_{stream.slug}_{freq}hz"
            discovery_topic = f"{self.config.discovery_prefix}/sensor/{object_id}/config"
            payload = {
                "name": f"{stream.name} {freq} Hz",
                "unique_id": object_id,
                "state_topic": state_topic,
                "value_template": "{{ value_json['%s'] }}" % freq,
                "unit_of_measurement": "dB",
                "state_class": "measurement",
                "icon": "mdi:waveform",
                "availability_topic": availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device,
            }
            self.client.publish(discovery_topic, json.dumps(payload), qos=1, retain=True)

        LOGGER.info("published MQTT discovery for stream %s", stream.name)

    def publish_state(self, stream: StreamIdentity, spectrum_by_hz: dict[str, float]) -> None:
        self.client.publish(self._state_topic(stream), json.dumps(spectrum_by_hz), qos=0, retain=False)

    def publish_availability(self, stream: StreamIdentity, online: bool) -> None:
        self.client.publish(self._availability_topic(stream), "online" if online else "offline", qos=1, retain=True)

    def _state_topic(self, stream: StreamIdentity) -> str:
        return f"{self.config.base_topic}/{stream.slug}/state"

    def _availability_topic(self, stream: StreamIdentity) -> str:
        return f"{self.config.base_topic}/{stream.slug}/availability"
