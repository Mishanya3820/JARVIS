import json
import os


SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

DEFAULT_SETTINGS = {
    # --- Groq ---
    "groq_api_key": "",
    "groq_model": "llama-3.3-70b-versatile",

    # --- ElevenLabs TTS ---
    "elevenlabs_model": "eleven_multilingual_v2",
    "elevenlabs_voice_id": "",
    "elevenlabs_stability": 0.48,
    "elevenlabs_similarity": 0.82,
    "elevenlabs_style": 0.12,
    "elevenlabs_speed": 0.96,
    "elevenlabs_speaker_boost": True,

    # --- Wake Word ---
    "wake_word_enabled": True,
    "rustpotter_cli_path": "resources/rustpotter/rustpotter-cli_win_x86_64.exe",
    "rustpotter_model_path": "resources/rustpotter/jarvis-ru.rpw",
    "rustpotter_device_index": 0,
    "wake_word_threshold": 0.5,

    # --- Vosk STT ---
    "vosk_model_path": "resources/vosk/vosk-model-small-ru-0.22",
}


def load_settings() -> dict:
    """Загружает настройки из settings.json."""
    if os.path.isfile(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            settings = DEFAULT_SETTINGS.copy()
            settings.update(loaded)
            return settings
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict) -> None:
    """Сохраняет настройки в settings.json рядом с программой."""
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def get_groq_api_key(settings: dict | None = None) -> str:
    """Возвращает ключ Groq.

    Переменная окружения имеет приоритет над ключом из settings.json.
    """
    env_key = os.environ.get("GROQ_API_KEY", "").strip()
    if env_key:
        return env_key

    settings = settings or load_settings()
    return (settings.get("groq_api_key") or "").strip()


def has_groq_api_key(settings: dict | None = None) -> bool:
    return bool(get_groq_api_key(settings))


def set_groq_api_key(api_key: str, settings: dict | None = None) -> dict:
    """Устанавливает локальный ключ Groq и сохраняет настройки."""
    settings = settings or load_settings()
    settings["groq_api_key"] = (api_key or "").strip()
    save_settings(settings)
    return settings


def delete_groq_api_key(settings: dict | None = None) -> dict:
    """Удаляет локальный ключ Groq из settings.json.

    Если GROQ_API_KEY задан в переменных окружения Windows, он продолжит
    использоваться — удалить его этой функцией невозможно намеренно.
    """
    return set_groq_api_key("", settings)


def get_elevenlabs_api_key() -> str:
    """Возвращает секрет ElevenLabs только из переменной окружения."""
    return os.environ.get("ELEVENLABS_API_KEY", "").strip()


def get_elevenlabs_voice_id(settings: dict | None = None) -> str:
    env_voice = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    if env_voice:
        return env_voice
    settings = settings or load_settings()
    return (settings.get("elevenlabs_voice_id") or "").strip()
