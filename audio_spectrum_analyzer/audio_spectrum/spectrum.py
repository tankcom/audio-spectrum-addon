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

    def _compute_dbfs(self, samples: np.ndarray) -> np.ndarray:
        frame = samples[-self.fft_size :].astype(np.float32)
        windowed = frame * self.window
        fft_result = np.fft.rfft(windowed)
        magnitude = np.abs(fft_result)
        return 20.0 * np.log10(np.maximum(magnitude, 1e-12))

    def _analyze_peak_bands(
        self,
        dbfs: np.ndarray,
        target_frequencies_hz: list[int],
    ) -> dict[str, dict[str, float]]:
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

    def _analyze_detail(
        self,
        dbfs: np.ndarray,
        step_hz: int,
        max_hz: int,
    ) -> dict[str, object]:
        values: list[float] = []
        max_index = dbfs.shape[0] - 1

        for band_high_hz in range(step_hz, max_hz + step_hz, step_hz):
            band_low_hz = max(0, band_high_hz - step_hz)
            low_index = int(np.floor(band_low_hz / self.bin_hz))
            high_index = int(np.floor(band_high_hz / self.bin_hz))

            low_index = min(max(low_index, 0), max_index)
            high_index = min(max(high_index, 0), max_index)
            if high_index < low_index:
                low_index, high_index = high_index, low_index

            band_slice = dbfs[low_index : high_index + 1]
            if band_slice.size == 0:
                values.append(-120.0)
                continue

            peak_db = float(np.max(band_slice))
            values.append(round(peak_db, 2))

        return {
            "step_hz": step_hz,
            "max_hz": max_hz,
            "values": values,
        }

    def analyze(self, samples: np.ndarray, target_frequencies_hz: list[int]) -> dict[str, dict[str, float]]:
        if samples.shape[0] < self.fft_size:
            return {}
        dbfs = self._compute_dbfs(samples)
        return self._analyze_peak_bands(dbfs, target_frequencies_hz)

    def analyze_bundle(
        self,
        samples: np.ndarray,
        target_frequencies_hz: list[int],
        detail_step_hz: int = 10,
        detail_max_hz: int = 20000,
    ) -> tuple[dict[str, dict[str, float]], dict[str, object]]:
        if samples.shape[0] < self.fft_size:
            return {}, {"step_hz": detail_step_hz, "max_hz": detail_max_hz, "values": []}

        dbfs = self._compute_dbfs(samples)
        peak_bands = self._analyze_peak_bands(dbfs, target_frequencies_hz)
        detail = self._analyze_detail(dbfs, step_hz=detail_step_hz, max_hz=detail_max_hz)
        return peak_bands, detail
