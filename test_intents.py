"""Безопасный тест локального Intent + Slots.
Не запускает приложения и не открывает сайты.
"""

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
JARVIS_SYSTEM_DIR = os.path.join(PROJECT_DIR, "Jarvis System")
sys.path.insert(0, JARVIS_SYSTEM_DIR)

from jarvis_commands import CommandManager  # noqa: E402


TEST_PHRASES = [
    "открой блокнот",
    "найди информацию о космосе",
    "найди на ютубе музыку для программирования",
    "открой сайт github.com",
    "зайди на youtube.com",
    r"открой D:\Games\Тестовые программы",
]


if __name__ == "__main__":
    manager = CommandManager()
    for phrase in TEST_PHRASES:
        match = manager.match(phrase)
        if match is None:
            print(f"{phrase!r} -> НЕ НАЙДЕНО")
        else:
            print(
                f"{phrase!r} -> {match.result.intent_id} "
                f"confidence={match.result.confidence:.2f} "
                f"slots={match.result.slots}"
            )
