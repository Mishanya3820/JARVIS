"""Локальный TTS JARVIS на базе Coqui XTTS-v2."""
from __future__ import annotations

import os
import threading

# TTS_HOME должен быть задан до импорта TTS.api.
from jarvis_paths import PROJECT_DIR, TTS_MODELS_DIR, setup_environment

setup_environment()
os.environ["TTS_HOME"] = str(TTS_MODELS_DIR)

import numpy as np
import sounddevice as sd

from jarvis_settings import load_settings

_tts = None
_tts_lock = threading.Lock()
_speak_lock = threading.Lock()
_IMPORT_ERROR = None
_torch = None
_TTS_CLASS = None

_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"


def _project_dir() -> str:
    return str(PROJECT_DIR)


def _resolve_path(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(_project_dir(), path)


def _get_device() -> str:
    global _torch
    settings = load_settings()
    requested = str(settings.get("xtts_device", "cpu")).strip().lower()
    if requested == "cuda":
        if _torch is None:
            import torch as torch_module
            _torch = torch_module
        if _torch.cuda.is_available():
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


def model_directory() -> str:
    """Возвращает каталог, в котором JARVIS хранит модели XTTS."""
    return str(TTS_MODELS_DIR)


def _get_model():
    global _tts, _TTS_CLASS, _IMPORT_ERROR, _torch

    if _tts is None:
        with _tts_lock:
            if _tts is None:
                try:
                    import torch as torch_module
                    from TTS.api import TTS as TTSClass
                    _torch = torch_module
                    _TTS_CLASS = TTSClass
                except ImportError as exc:
                    _IMPORT_ERROR = exc
                    raise RuntimeError(
                        "Библиотека TTS не установлена. Установи зависимости из requirements.txt."
                    ) from exc

                device = _get_device()
                print(f"[XTTS] Каталог моделей: {TTS_MODELS_DIR}")
                print(f"[XTTS] Загружаю модель {_MODEL_NAME} на {device}...")
                _tts = _TTS_CLASS(_MODEL_NAME).to(device)
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

        padding_ms = int(settings.get("xtts_playback_padding_ms", 80))
        padding = np.zeros(max(0, int(24000 * padding_ms / 1000)), dtype=np.float32)
        audio_np = np.concatenate((padding, audio_np, padding))

        sd.play(audio_np, samplerate=24000)
        sd.wait()
