import json
import os

from jarvis_paths import SETTINGS_FILE


SETTINGS_PATH = str(SETTINGS_FILE)
DEFAULT_SETTINGS = {
    "performance_mode": "balanced",
    "groq_api_key": "",
    "groq_model": "openai/gpt-oss-120b",
    "tts_engine": "coqui",
    "xtts_speaker_wav": "resources/tts/jarvis_voice.wav",
    "xtts_language": "ru",
    "xtts_device": "cpu",
    "xtts_split_sentences": True,
    "xtts_playback_padding_ms": 80,
    "elevenlabs_api_key": "",
    "elevenlabs_voice_id": "",
    "elevenlabs_model": "eleven_multilingual_v2",
    "elevenlabs_output_format": "pcm_24000",
    "silero_model": "v5_5_ru",
    "silero_speaker": "eugene",
    "silero_device": "cpu",
    "silero_sample_rate": 48000,
    "silero_playback_padding_ms": 40,
    "wake_word_enabled": True,
    "rustpotter_cli_path": "resources/rustpotter/rustpotter-cli_win_x86_64.exe",
    "rustpotter_model_path": "resources/rustpotter/jarvis-ru.rpw",
    "rustpotter_device_index": 0,
    "wake_word_threshold": 0.5,
}

TTS_ENGINES = {
    "coqui": "Coqui XTTS-v2",
    "elevenlabs": "ElevenLabs",
    "silero": "Silero TTS",
}

SILERO_SPEAKERS = {
    "aidar": "Айдар — мужской",
    "baya": "Бая — женский",
    "kseniya": "Ксения — женский",
    "xenia": "Ксения — вариант",
    "eugene": "Евгений — мужской, глубокий",
}


def load_settings() -> dict:
    if os.path.isfile(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            settings = DEFAULT_SETTINGS.copy()
            settings.update(loaded)
            if settings.get("performance_mode") not in {"performance", "balanced", "economy"}:
                settings["performance_mode"] = "balanced"
            if settings.get("tts_engine") not in TTS_ENGINES:
                settings["tts_engine"] = "coqui"
            return settings
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict) -> None:
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def get_groq_api_key(settings: dict | None = None) -> str:
    env_key = os.environ.get("GROQ_API_KEY", "").strip()
    if env_key:
        return env_key
    settings = settings or load_settings()
    return (settings.get("groq_api_key") or "").strip()


def has_groq_api_key(settings: dict | None = None) -> bool:
    return bool(get_groq_api_key(settings))


def set_groq_api_key(api_key: str, settings: dict | None = None) -> dict:
    settings = settings or load_settings()
    settings["groq_api_key"] = (api_key or "").strip()
    save_settings(settings)
    return settings


def delete_groq_api_key(settings: dict | None = None) -> dict:
    return set_groq_api_key("", settings)


def get_elevenlabs_api_key(settings: dict | None = None) -> str:
    env_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if env_key:
        return env_key
    settings = settings or load_settings()
    return (settings.get("elevenlabs_api_key") or "").strip()


def has_elevenlabs_api_key(settings: dict | None = None) -> bool:
    return bool(get_elevenlabs_api_key(settings))


def get_performance_mode(settings: dict | None = None) -> str:
    settings = settings or load_settings()
    mode = str(settings.get("performance_mode", "balanced")).strip().lower()
    return mode if mode in {"performance", "balanced", "economy"} else "balanced"
