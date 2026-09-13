from __future__ import annotations

import os
import threading

from jarvis_paths import PROJECT_DIR, TTS_MODELS_DIR, setup_environment

setup_environment()
os.environ["TTS_HOME"] = str(TTS_MODELS_DIR)

import numpy as np
import sounddevice as sd

from jarvis_settings import get_elevenlabs_api_key, load_settings

_tts = None
_tts_lock = threading.Lock()
_speak_lock = threading.Lock()
_import_error = None
_torch = None
_TTS_CLASS = None

_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"


def _resolve_path(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(str(PROJECT_DIR), path)


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
    return str(TTS_MODELS_DIR)


def _get_coqui_model():
    global _tts, _TTS_CLASS, _import_error, _torch
    if _tts is None:
        with _tts_lock:
            if _tts is None:
                try:
                    import torch as torch_module
                    from TTS.api import TTS as TTSClass
                    _torch = torch_module
                    _TTS_CLASS = TTSClass
                except ImportError as exc:
                    _import_error = exc
                    raise RuntimeError(
                        "Библиотека coqui-tts не установлена. Установи: pip install coqui-tts"
                    ) from exc
                device = _get_device()
                print(f"[XTTS] Каталог моделей: {TTS_MODELS_DIR}")
                print(f"[XTTS] Загружаю модель {_MODEL_NAME} на {device}...")
                _tts = _TTS_CLASS(_MODEL_NAME).to(device)
                print("[XTTS] Модель загружена.")
    return _tts


def _speak_coqui(text: str, settings: dict) -> None:
    speaker_wavs = _get_speaker_wavs()
    if not speaker_wavs:
        raise RuntimeError(
            "Не найден WAV-образец голоса для XTTS. "
            "Положи reference WAV в resources/tts/jarvis_voice.wav "
            "или укажи другой путь в настройках."
        )
    language = str(settings.get("xtts_language", "ru")).strip() or "ru"
    split_sentences = bool(settings.get("xtts_split_sentences", True))
    tts = _get_coqui_model()
    audio = tts.tts(
        text=text,
        speaker_wav=speaker_wavs,
        language=language,
        split_sentences=split_sentences,
    )
    _play_pcm_float(audio, 24000, int(settings.get("xtts_playback_padding_ms", 80)))


def _get_elevenlabs_client():
    api_key = get_elevenlabs_api_key()
    if not api_key:
        raise RuntimeError(
            "Не найден ElevenLabs API-ключ. Открой Настройки → Голос JARVIS "
            "и добавь ключ или задай ELEVENLABS_API_KEY в Windows."
        )
    try:
        from elevenlabs.client import ElevenLabs
    except ImportError as exc:
        raise RuntimeError("Не установлен пакет elevenlabs. Установи: pip install elevenlabs") from exc
    return ElevenLabs(api_key=api_key)


def _speak_elevenlabs(text: str, settings: dict) -> None:
    voice_id = str(settings.get("elevenlabs_voice_id", "")).strip()
    if not voice_id:
        raise RuntimeError("Не задан ElevenLabs Voice ID в настройках.")
    model_id = str(settings.get("elevenlabs_model", "eleven_multilingual_v2")).strip() or "eleven_multilingual_v2"
    client = _get_elevenlabs_client()
    audio = client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
        model_id=model_id,
        output_format="pcm_24000",
    )
    audio_bytes = b"".join(audio) if not isinstance(audio, (bytes, bytearray)) else bytes(audio)
    if not audio_bytes:
        raise RuntimeError("ElevenLabs вернул пустой аудиопоток.")
    audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    _play_pcm_float(audio_np, 24000, int(settings.get("xtts_playback_padding_ms", 80)))


def _play_pcm_float(audio, samplerate: int, padding_ms: int) -> None:
    audio_np = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio_np.size == 0:
        raise RuntimeError("TTS вернул пустой аудиопоток.")
    padding = np.zeros(max(0, int(samplerate * padding_ms / 1000)), dtype=np.float32)
    audio_np = np.concatenate((padding, audio_np, padding))
    sd.play(audio_np, samplerate=samplerate)
    sd.wait()


def get_engine() -> str:
    engine = str(load_settings().get("tts_engine", "coqui")).strip().lower()
    return engine if engine in {"coqui", "elevenlabs"} else "coqui"


def is_configured() -> bool:
    settings = load_settings()
    if get_engine() == "elevenlabs":
        return bool(get_elevenlabs_api_key(settings) and str(settings.get("elevenlabs_voice_id", "")).strip())
    return bool(_get_speaker_wavs())


def warmup() -> None:
    settings = load_settings()
    if get_engine() == "coqui":
        if _get_speaker_wavs():
            _get_coqui_model()
    else:
        # ElevenLabs is remote, so there is no local model to preload.
        if not get_elevenlabs_api_key(settings):
            return
        if not str(settings.get("elevenlabs_voice_id", "")).strip():
            return
        _get_elevenlabs_client()


def speak(text: str) -> None:
    text = (text or "").strip()
    if not text:
        return
    settings = load_settings()
    engine = get_engine()
    with _speak_lock:
        if engine == "elevenlabs":
            _speak_elevenlabs(text, settings)
        else:
            _speak_coqui(text, settings)
