"""Лечит зависание окна JARVIS при старте (веб-интерфейс на pywebview).

Запуск из любой папки:
    python fix_startup_freeze.py "путь/к/Jarvis System/web_gui/jarvis_gui_web.py"
Если путь не указан, берётся web_gui/jarvis_gui_web.py рядом со скриптом
или в папке "Jarvis System". Рядом создаётся резервная копия .bak.

Что делает: превращает публичные поля класса JarvisWebApi в приватные
(self.window -> self._window и т.д.). pywebview обходит ВСЕ публичные
поля js_api-объекта рекурсивно, а self.window тянет за собой
window.native — живую .NET-форму окна.
"""
import os, re, shutil, sys

NAMES = ("window", "settings", "models_ready", "wake_detector", "reminder_stop", "tray_icon")
PATTERN = re.compile(r"\bself\.(" + "|".join(NAMES) + r")\b")


def find_target(argv):
    if len(argv) > 1:
        return argv[1]
    here = os.path.dirname(os.path.abspath(__file__))
    for rel in ("web_gui/jarvis_gui_web.py", "Jarvis System/web_gui/jarvis_gui_web.py", "jarvis_gui_web.py"):
        path = os.path.join(here, rel)
        if os.path.isfile(path):
            return path
    sys.exit("Не нашёл jarvis_gui_web.py — укажи путь аргументом.")


def main():
    path = find_target(sys.argv)
    raw = open(path, "rb").read()
    text = raw.decode("utf-8")
    new, count = PATTERN.subn(lambda m: "self._" + m.group(1), text)
    if count == 0:
        print("Ничего менять не нужно: публичных полей self.window/self.settings/... уже нет.")
        return
    shutil.copyfile(path, path + ".bak")
    open(path, "wb").write(new.encode("utf-8"))
    print(f"Готово: заменено {count} обращений в {path}")
    print(f"Резервная копия: {path}.bak")


if __name__ == "__main__":
    main()