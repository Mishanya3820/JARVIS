import json
import os


SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

DEFAULT_SETTINGS = {
    # --- Groq ---
    "groq_api_key": "",
    "groq_model": "openai/gpt-oss-120b",

    # --- Coqui XTTS-v2 ---
    # Путь к одному или нескольким WAV через ';'.
    "xtts_speaker_wav": "resources/tts/jarvis_voice.wav",
    "xtts_language": "ru",
    # Для GT 1030 безопаснее начать с CPU. Если CUDA работает стабильно,
    # можно поменять на "cuda".
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
