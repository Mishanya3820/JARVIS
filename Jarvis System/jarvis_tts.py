"""Локальный TTS JARVIS на базе Coqui XTTS-v2.

XTTS-v2 работает полностью локально после загрузки модели и умеет
клонировать голос по одному или нескольким WAV-файлам.
"""
from __future__ import annotations

import os
import threading

import numpy as np
import sounddevice as sd

from jarvis_settings import load_settings

try:
    import torch
    from TTS.api import TTS
except ImportError as exc:  # pragma: no cover - зависит от окружения
    torch = None
    TTS = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
_tts = None
_tts_lock = threading.Lock()
_speak_lock = threading.Lock()


def _project_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve_path(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(_project_dir(), path)


def _get_device() -> str:
    settings = load_settings()
    requested = str(settings.get("xtts_device", "cpu")).strip().lower()
    if requested == "cuda":
        if torch is not None and torch.cuda.is_available():
            return "cuda"
        print("[XTTS] CUDA недоступна, использую CPU.")
    return "cpu"


def _get_speaker_wavs() -> list[str]:
    settings = load_settings()
    raw = settings.get("xtts_speaker_wav", "resources/tts/jarvis_voice.wav")
    paths = []
    for item in str(raw).split(";"):
        item = item.strip()
        if not item:
            continue
        path = _resolve_path(item)
        if os.path.isfile(path):
            paths.append(path)
        else:
            print(f"[XTTS] WAV-образец не найден: {path}")
    return paths


def _get_model():
    global _tts
    if TTS is None:
        raise RuntimeError(
            "Coqui TTS не установлен. Установи зависимости из requirements.txt."
        ) from _IMPORT_ERROR

    if _tts is None:
        with _tts_lock:
            if _tts is None:
                device = _get_device()
                print(f"[XTTS] Загружаю модель { _MODEL_NAME } на {device}...")
                _tts = TTS(_MODEL_NAME).to(device)
                print("[XTTS] Модель загружена.")
    return _tts


def is_configured() -> bool:
    return bool(_get_speaker_wavs())


def warmup() -> None:
    """Загружает модель заранее, но ничего не озвучивает."""
    if not is_configured():
        return
    _get_model()


def speak(text: str) -> None:
    """Генерирует и воспроизводит русский ответ голосом из reference WAV."""
    text = (text or "").strip()
    if not text:
        return

    speaker_wavs = _get_speaker_wavs()
    if not speaker_wavs:
        raise RuntimeError(
            "Не найден WAV-образец голоса для XTTS. "
            "Положи reference WAV в resources/tts/jarvis_voice.wav "
            "или укажи другой путь в настройках."
        )

    settings = load_settings()
    language = str(settings.get("xtts_language", "ru")).strip() or "ru"
    split_sentences = bool(settings.get("xtts_split_sentences", True))

    # Один lock не даёт двум потокам одновременно обращаться к XTTS и
    # не позволяет новому аудио остановить ещё не закончившееся.
    with _speak_lock:
        tts = _get_model()
        audio = tts.tts(
            text=text,
            speaker_wav=speaker_wavs,
            language=language,
            split_sentences=split_sentences,
        )

        audio_np = np.asarray(audio, dtype=np.float32)
        if audio_np.size == 0:
            raise RuntimeError("XTTS вернул пустой аудиопоток.")

        # XTTS выдаёт 24 кГц. Небольшая тишина по краям предотвращает
        # субъективное "срезание" первых/последних миллисекунд на некоторых
        # Windows/PortAudio устройствах.
        padding_ms = int(settings.get("xtts_playback_padding_ms", 80))
        padding = np.zeros(max(0, int(24000 * padding_ms / 1000)), dtype=np.float32)
        audio_np = np.concatenate((padding, audio_np, padding))

        sd.play(audio_np, samplerate=24000)
        sd.wait()
