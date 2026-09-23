from __future__ import annotations
 
import numpy as np
 
 
class HighPassFilter:
    """Простой причинный (без задержки на буферизацию) one-pole HPF.
 
    Настроен на срез около 90 Гц: гул/наводки/стук по корпусу ослабляются
    заметно (в тестах — примерно на 8 дБ на 40 Гц), а речь (от ~150 Гц и
    выше по основному тону) почти не затрагивается (в пределах 1 дБ)."""
 
    def __init__(self, sample_rate: int, cutoff_hz: float = 90.0):
        self._alpha = 1.0 - (2 * np.pi * cutoff_hz / sample_rate)
        self._prev_x = 0.0
        self._prev_y = 0.0
 
    def reset(self) -> None:
        self._prev_x = 0.0
        self._prev_y = 0.0
 
    def process(self, frame: np.ndarray) -> np.ndarray:
        out = np.empty_like(frame, dtype=np.float32)
        x_prev = self._prev_x
        y_prev = self._prev_y
        alpha = self._alpha
        for i in range(frame.shape[0]):
            x = frame[i]
            y = alpha * (y_prev + x - x_prev)
            out[i] = y
            x_prev, y_prev = x, y
        self._prev_x, self._prev_y = float(x_prev), float(y_prev)
        return out
 
 
class AutoGainControl:
    """Плавно подтягивает громкость к целевому уровню — тихая речь издалека
    и громкая речь вблизи после этого звучат для GigaAM примерно одинаково.
 
    Специально не применяется к сигналу, который видит VAD: усиление
    поднимает и уровень шума тоже, а значит может провоцировать ложные
    срабатывания VAD на тишине. Здесь AGC применяется только к тому, что
    реально уходит в распознавание речи, уже ПОСЛЕ решения VAD."""
 
    def __init__(self, target_rms: float = 0.09, min_gain: float = 1.0, max_gain: float = 6.0, smoothing: float = 0.9):
        self.target_rms = target_rms
        self.min_gain = min_gain
        self.max_gain = max_gain
        self.smoothing = smoothing
        self._gain = 1.0
 
    def reset(self) -> None:
        self._gain = 1.0
 
    def process(self, frame: np.ndarray) -> np.ndarray:
        rms = float(np.sqrt(np.mean(np.square(frame)))) + 1e-6
        target_gain = min(max(self.target_rms / rms, self.min_gain), self.max_gain)
        self._gain = self.smoothing * self._gain + (1 - self.smoothing) * target_gain
        return np.clip(frame * self._gain, -1.0, 1.0).astype(np.float32)