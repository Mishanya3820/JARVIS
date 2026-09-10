"""Единая система путей JARVIS.

Одинаково работает из исходников и из PyInstaller onedir-сборки.
Все пользовательские данные и модели остаются рядом с программой, а не
временной папке PyInstaller.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def project_dir() -> Path:
    """Возвращает корень проекта/папку установленного JARVIS."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_DIR = project_dir()
MODELS_DIR = PROJECT_DIR / "Models"
TTS_MODELS_DIR = MODELS_DIR / "TTS"
RESOURCES_DIR = PROJECT_DIR / "resources"
SETTINGS_FILE = PROJECT_DIR / "Jarvis System" / "settings.json"


def setup_environment() -> None:
    """Настраивает каталоги моделей до импорта Coqui TTS."""
    TTS_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # Coqui TTS использует TTS_HOME как корень своего каталога моделей.
    os.environ.setdefault("TTS_HOME", str(TTS_MODELS_DIR))

    # Заодно переносим pip-кэш с системного диска, если JARVIS запускается
    # из установленной папки. Пользовательские переменные Windows не нужны.
    pip_cache = PROJECT_DIR / "Cache" / "pip"
    pip_cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PIP_CACHE_DIR", str(pip_cache))


setup_environment()
