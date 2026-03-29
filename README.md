# Audio Spectrum Analyzer Home Assistant Add-on

## Use As Custom Repository

This repository is prepared as a Home Assistant Add-on repository.

Add this URL in Home Assistant:
- Settings -> Add-ons -> Add-on Store -> menu (top right) -> Repositories
- Repository URL: https://github.com/tankcom/audio-spectrum-addon

The add-on folder is:
- audio_spectrum_analyzer

This add-on reads audio from RTSP/RTMP streams, computes an FFT, and publishes Home Assistant MQTT discovery sensors in 500 Hz steps from 500 Hz to 20000 Hz.

## Ingress GUI

The add-on now provides an Ingress web interface in Home Assistant with three pages:
- Live Spectrum: real-time bar spectrum similar to mobile spectrum apps
- Waterfall: scrolling heatmap with history window slider
- Streams: configure RTSP/RTMP stream URLs directly in the UI

Saving stream settings in the Streams page applies immediately without add-on restart.
Runtime stream settings are stored in /config/audio_spectrum_streams.json.

## Status

Initial implementation with:
- Multi-stream FFmpeg audio ingest
- Spectrum analysis every update interval
- 500 Hz bin sensors via MQTT discovery
- In-memory waterfall frame buffer and HTTP endpoint

## Configure

Set streams in add-on options:

- name: Front Camera
  url: rtsp://user:pass@192.168.1.10:554/stream1
  enabled: true

MQTT defaults to core-mosquitto on port 1883.

Recommended add-on options:

sample_rate: 48000
fft_size: 8192
update_interval_ms: 250
window_function: hann
streams:
  - name: Front Camera
    url: rtsp://user:pass@192.168.1.10:554/stream1
    enabled: true
  - name: Back Camera
    url: rtmp://192.168.1.20/live/cam
    enabled: true
mqtt:
  host: core-mosquitto
  port: 1883
  username: ""
  password: ""
  discovery_prefix: homeassistant
  base_topic: audio_spectrum
rest:
  enabled: true
  host: 0.0.0.0
  port: 8099

## MQTT Entities

For each stream, the add-on publishes MQTT discovery sensors for all frequencies:
- 500 Hz, 1000 Hz, 1500 Hz, ... up to 20000 Hz
- Total per stream: 40 sensors
- Unit: dB

Each sensor now scans its own 500 Hz band and reports the highest dB value in that band.
Example:
- Sensor 8000 Hz scans (7500, 8000] Hz
- If the peak is at 7960 Hz, the sensor state still shows that peak dB

Sensor attributes include:
- peak_freq_hz
- range_low_hz
- range_high_hz

State topic per stream:
- audio_spectrum/<stream-slug>/state

Availability topic per stream:
- audio_spectrum/<stream-slug>/availability

## Waterfall Data Endpoint

The add-on exposes a simple JSON endpoint for waterfall consumers:
- GET /waterfall

Response format:
- Object keyed by stream slug
- Each stream contains frames with timestamp and frequency->dB map

Additional API endpoints used by the GUI:
- GET /api/live
- GET /api/waterfall
- GET /api/config
- POST /api/config/streams

## Examples

- Example add-on options: examples/options.example.json
- Example dashboard skeleton: examples/waterfall-dashboard.example.yaml

## Quick Verification

- Ensure 40 sensors per stream appear in Home Assistant after startup.
- Confirm topic audio_spectrum/<stream-slug>/state contains keys "500" through "20000" with nested fields (db, peak_freq_hz, range_low_hz, range_high_hz).
- Open /health and /waterfall on the configured REST port.
