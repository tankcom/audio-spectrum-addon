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

    def analyze(self, samples: np.ndarray, target_frequencies_hz: list[int]) -> dict[str, float]:
        if samples.shape[0] < self.fft_size:
            return {}

        frame = samples[-self.fft_size :].astype(np.float32)
        windowed = frame * self.window

        fft_result = np.fft.rfft(windowed)
        magnitude = np.abs(fft_result)
        dbfs = 20.0 * np.log10(np.maximum(magnitude, 1e-12))

        result: dict[str, float] = {}
        max_index = dbfs.shape[0] - 1
        for freq in target_frequencies_hz:
            index = int(round(freq / self.bin_hz))
            index = min(max(index, 0), max_index)
            result[str(freq)] = round(float(dbfs[index]), 2)

        return result
