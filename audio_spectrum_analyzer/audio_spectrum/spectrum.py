from __future__ import annotations

import numpy as np


class SpectrumAnalyzer:
    def __init__(self, sample_rate: int, fft_size: int, window_function: str) -> None:
        self.sample_rate = sample_rate
        self.fft_size = fft_size
        self.window = self._build_window(fft_size, window_function)
        self.bin_hz = sample_rate / fft_size

    @staticmethod
    def _build_window(fft_size: int, window_function: str) -> np.ndarray:
        if window_function == "hamming":
            return np.hamming(fft_size).astype(np.float32)
        if window_function == "blackman":
            return np.blackman(fft_size).astype(np.float32)
        return np.hanning(fft_size).astype(np.float32)

    def analyze(self, samples: np.ndarray, target_frequencies_hz: list[int]) -> dict[str, dict[str, float]]:
        if samples.shape[0] < self.fft_size:
            return {}

        frame = samples[-self.fft_size :].astype(np.float32)
        windowed = frame * self.window

        fft_result = np.fft.rfft(windowed)
        magnitude = np.abs(fft_result)
        dbfs = 20.0 * np.log10(np.maximum(magnitude, 1e-12))

        result: dict[str, dict[str, float]] = {}
        max_index = dbfs.shape[0] - 1
        for freq in target_frequencies_hz:
            band_high_hz = float(freq)
            band_low_hz = max(0.0, band_high_hz - 500.0)

            low_index = int(np.floor(band_low_hz / self.bin_hz))
            high_index = int(np.floor(band_high_hz / self.bin_hz))

            low_index = min(max(low_index, 0), max_index)
            high_index = min(max(high_index, 0), max_index)

            if high_index < low_index:
                low_index, high_index = high_index, low_index

            band_slice = dbfs[low_index : high_index + 1]
            if band_slice.size == 0:
                continue

            peak_offset = int(np.argmax(band_slice))
            peak_index = low_index + peak_offset
            peak_freq_hz = peak_index * self.bin_hz
            peak_db = float(dbfs[peak_index])

            result[str(freq)] = {
                "db": round(peak_db, 2),
                "peak_freq_hz": round(float(peak_freq_hz), 2),
                "range_low_hz": round(float(band_low_hz), 2),
                "range_high_hz": round(float(band_high_hz), 2),
            }

        return result
