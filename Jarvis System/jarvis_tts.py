from __future__ import annotations
 
import os
import threading
import time
from pathlib import Path
 
from jarvis_paths import PROJECT_DIR, SILERO_MODELS_DIR, TTS_MODELS_DIR, setup_environment
 
setup_environment()
os.environ["TTS_HOME"] = str(TTS_MODELS_DIR)
 
import numpy as np
import sounddevice as sd
 
from jarvis_settings import get_elevenlabs_api_key, load_settings
 
_tts = None
_silero = None
_tts_lock = threading.Lock()
_speak_lock = threading.Lock()
_torch = None
_TTS_CLASS = None
_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
_SILERO_DEFAULT_MODEL = "v5_5_ru"
_SILERO_MODEL_URLS = {
    "v5_5_ru": "https://models.silero.ai/models/tts/ru/v5_5_ru.pt",
    "v5_4_ru": "https://models.silero.ai/models/tts/ru/v5_4_ru.pt",
    "v5_ru": "https://models.silero.ai/models/tts/ru/v5_ru.pt",
}
 
 
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
 
 
def silero_model_directory() -> str:
    return str(SILERO_MODELS_DIR)
 
 
def _get_coqui_model():
    global _tts, _TTS_CLASS, _torch
    if _tts is None:
        with _tts_lock:
            if _tts is None:
                try:
                    import torch as torch_module
                    from TTS.api import TTS as TTSClass
                    _torch = torch_module
                    _TTS_CLASS = TTSClass
                except ImportError as exc:
                    raise RuntimeError("Библиотека coqui-tts не установлена. Установи: pip install coqui-tts") from exc
                device = _get_device()
                print(f"[XTTS] Загружаю модель {_MODEL_NAME} на {device}...")
                _tts = _TTS_CLASS(_MODEL_NAME).to(device)
                print("[XTTS] Модель загружена.")
    return _tts
 
 
def _get_silero_model():
    global _silero
    if _silero is None:
        with _tts_lock:
            if _silero is None:
                settings = load_settings()
                model_id = str(settings.get("silero_model", _SILERO_DEFAULT_MODEL)).strip() or _SILERO_DEFAULT_MODEL
                speaker = str(settings.get("silero_speaker", "eugene")).strip() or "eugene"
                device = str(settings.get("silero_device", "cpu")).strip().lower() or "cpu"
                if model_id not in _SILERO_MODEL_URLS:
                    print(f"[Silero] Неизвестная модель {model_id}, использую {_SILERO_DEFAULT_MODEL}.")
                    model_id = _SILERO_DEFAULT_MODEL
                model_path = Path(SILERO_MODELS_DIR) / f"{model_id}.pt"
                try:
                    import torch
                    if device == "cuda" and not torch.cuda.is_available():
                        device = "cpu"
 
                    if not model_path.is_file():
                        print(f"[Silero] Модель {model_id} не найдена локально.")
                        print(f"[Silero] Скачиваю модель в {model_path}...")
                        SILERO_MODELS_DIR.mkdir(parents=True, exist_ok=True)
                        torch.hub.download_url_to_file(
                            _SILERO_MODEL_URLS[model_id],
                            str(model_path),
                            progress=True,
                        )
 
                    print(f"[Silero] Загружаю {model_id} / {speaker} на {device}...")
                    model = torch.package.PackageImporter(str(model_path)).load_pickle("tts_models", "model")
                    model.to(device)
                    _silero = (model, speaker, device)
                    print(f"[Silero] Модель {model_id} загружена.")
                except ImportError as exc:
                    raise RuntimeError("Silero TTS не установлен. Установи: pip install silero") from exc
                except Exception as exc:
                    raise RuntimeError(f"Не удалось загрузить Silero TTS: {exc}") from exc
    return _silero
 
 
def _speak_coqui(text: str, settings: dict) -> None:
    speaker_wavs = _get_speaker_wavs()
    if not speaker_wavs:
        raise RuntimeError("Не найден WAV-образец голоса для XTTS.")
    language = str(settings.get("xtts_language", "ru")).strip() or "ru"
    split_sentences = bool(settings.get("xtts_split_sentences", True))
    audio = _get_coqui_model().tts(text=text, speaker_wav=speaker_wavs, language=language, split_sentences=split_sentences)
    _play_pcm_float(audio, 24000, int(settings.get("xtts_playback_padding_ms", 80)))
 
 
def _speak_silero(text: str, settings: dict) -> None:
    model, speaker, _device = _get_silero_model()
    sample_rate = int(settings.get("silero_sample_rate", 48000))
    audio = model.apply_tts(text=text, speaker=speaker, sample_rate=sample_rate)
    _play_pcm_float(audio, sample_rate, int(settings.get("silero_playback_padding_ms", 40)))
 
 
def _get_elevenlabs_client():
    api_key = get_elevenlabs_api_key()
    if not api_key:
        raise RuntimeError("Не найден ElevenLabs API-ключ. Добавь его в Настройки → Голос JARVIS.")
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
    output_format = str(settings.get("elevenlabs_output_format", "pcm_24000")).strip() or "pcm_24000"
    audio = _get_elevenlabs_client().text_to_speech.convert(voice_id=voice_id, text=text, model_id=model_id, output_format=output_format)
    audio_bytes = b"".join(audio) if not isinstance(audio, (bytes, bytearray)) else bytes(audio)
    if not audio_bytes:
        raise RuntimeError("ElevenLabs вернул пустой аудиопоток.")
    if output_format == "pcm_24000":
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        _play_pcm_float(audio_np, 24000, int(settings.get("xtts_playback_padding_ms", 80)))
    else:
        raise RuntimeError("Для JARVIS сейчас используется только pcm_24000 для ElevenLabs.")
 
 
_now_playing_lock = threading.Lock()
_now_playing = {"audio": None, "samplerate": 0, "started_at": 0.0}
 
 
def get_now_playing() -> dict:
    """Снимок сейчас проигрываемого буфера — для живой визуализации речи
    JARVIS в GUI. Ничего не пересчитывает и не влияет на воспроизведение,
    просто отдаёт то, что уже лежит в памяти."""
    with _now_playing_lock:
        return dict(_now_playing)
 
 
def _play_pcm_float(audio, samplerate: int, padding_ms: int) -> None:
    audio_np = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio_np.size == 0:
        raise RuntimeError("TTS вернул пустой аудиопоток.")
    padding = np.zeros(max(0, int(samplerate * padding_ms / 1000)), dtype=np.float32)
    full = np.concatenate((padding, audio_np, padding))
    with _now_playing_lock:
        _now_playing["audio"] = full
        _now_playing["samplerate"] = samplerate
        _now_playing["started_at"] = time.monotonic()
    try:
        sd.play(full, samplerate=samplerate)
        sd.wait()
    finally:
        with _now_playing_lock:
            _now_playing["audio"] = None
 
 
def get_engine() -> str:
    engine = str(load_settings().get("tts_engine", "coqui")).strip().lower()
    return engine if engine in {"coqui", "elevenlabs", "silero"} else "coqui"
 
 
def is_configured() -> bool:
    settings = load_settings()
    engine = get_engine()
    if engine == "elevenlabs":
        return bool(get_elevenlabs_api_key(settings) and str(settings.get("elevenlabs_voice_id", "")).strip())
    if engine == "silero":
        return True
    return bool(_get_speaker_wavs())
 
 
def warmup() -> None:
    settings = load_settings()
    engine = get_engine()
    if engine == "coqui" and _get_speaker_wavs():
        _get_coqui_model()
    elif engine == "silero":
        _get_silero_model()
    elif engine == "elevenlabs" and get_elevenlabs_api_key(settings) and str(settings.get("elevenlabs_voice_id", "")).strip():
        _get_elevenlabs_client()
 
 
def speak(text: str) -> None:
    text = (text or "").strip()
    if not text:
        return
    settings = load_settings()
    with _speak_lock:
        engine = get_engine()
        if engine == "elevenlabs":
            _speak_elevenlabs(text, settings)
        elif engine == "silero":
            _speak_silero(text, settings)
        else:
            _speak_coqui(text, settings)