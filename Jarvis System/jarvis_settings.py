import json
import os

from jarvis_paths import SETTINGS_FILE, PROJECT_DIR


SETTINGS_PATH = str(SETTINGS_FILE)
DEFAULT_SETTINGS = {
    # --- Groq ---
    "groq_api_key": "",
    "groq_model": "openai/gpt-oss-120b",

    # --- Coqui XTTS-v2 ---
    "xtts_speaker_wav": "resources/tts/jarvis_voice.wav",
    "xtts_language": "ru",
    "xtts_device": "cpu",
    "xtts_split_sentences": True,
    "xtts_playback_padding_ms": 80,

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
    """Загружает настройки из settings.json рядом с программой."""
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
    """Сохраняет настройки рядом с программой."""
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
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
    """Удаляет локальный ключ Groq из settings.json."""
    return set_groq_api_key("", settings)
