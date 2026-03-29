#!/usr/bin/env sh
set -eu

OPTIONS_FILE="/data/options.json"

if [ ! -f "$OPTIONS_FILE" ]; then
  echo "[audio-spectrum] options file missing, using defaults"
fi

exec python -m audio_spectrum.app "$OPTIONS_FILE"
