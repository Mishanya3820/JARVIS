"""Загрузчик и исполнитель локальных команд JARVIS."""
 
from __future__ import annotations
 
import json
import os
import shutil
import subprocess
import webbrowser
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote
 
import psutil
 
from jarvis_intent import IntentResult, classify
 
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
COMMANDS_DIR = os.path.join(PROJECT_DIR, "commands")
 
# Запускаем дочерние GUI-процессы без наследования консоли JARVIS —
# иначе диагностические сообщения Electron-приложений (Discord и т.п.)
# утекают прямо в консоль JARVIS.
_POPEN_KWARGS: dict[str, Any] = {
    "stdout": subprocess.DEVNULL,
    "stderr": subprocess.DEVNULL,
    "stdin": subprocess.DEVNULL,
}
if os.name == "nt":
    _POPEN_KWARGS["creationflags"] = subprocess.CREATE_NO_WINDOW
 
 
@dataclass
class CommandMatch:
    command: dict[str, Any]
    result: IntentResult
 
 
class CommandManager:
    def __init__(self, commands_dir: str = COMMANDS_DIR):
        self.commands_dir = commands_dir
        self.commands: list[dict[str, Any]] = []
        self.reload()
 
    def reload(self) -> None:
        self.commands = []
        if not os.path.isdir(self.commands_dir):
            return
        for root, _, files in os.walk(self.commands_dir):
            for filename in files:
                if not filename.endswith(".json"):
                    continue
                path = os.path.join(root, filename)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("id") and data.get("phrases"):
                        self.commands.append(data)
                except (OSError, json.JSONDecodeError) as e:
                    print(f"[Commands] Не удалось загрузить {path}: {e}")
 
    def match(self, text: str) -> CommandMatch | None:
        result = classify(text, self.commands)
        if result is None:
            return None
        command = next((c for c in self.commands if c.get("id") == result.intent_id), None)
        return CommandMatch(command, result) if command else None
 
    def all_phrases(self) -> list[str]:
        """Все фразы всех команд — используется для построения
        Vosk-грамматики (ограниченного словаря распознавания)."""
        phrases: list[str] = []
        for command in self.commands:
            phrases.extend(command.get("phrases", []))
        return phrases
 
    @staticmethod
    def _protocol_registered(uri: str) -> bool:
        """Проверяет Windows URI-протокол, например discord:// или steam://."""
        if os.name != "nt":
            return True
        try:
            import winreg
 
            scheme = str(uri).split(":", 1)[0].strip().lower()
            if not scheme:
                return False
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, scheme):
                return True
        except (FileNotFoundError, OSError):
            return False
 
    @staticmethod
    def _executable_exists(executable: str) -> bool:
        if os.path.isabs(executable):
            return os.path.isfile(executable)
        return shutil.which(executable) is not None
 
    @staticmethod
    def _find_processes(process_names: list[str]) -> list[psutil.Process]:
        """Ищет запущенные процессы по списку возможных имён (без учёта
        регистра) — некоторые приложения запускаются под разными именами
        exe в зависимости от версии (например, современный Калькулятор
        Windows — CalculatorApp.exe, а не calc.exe)."""
        wanted = {name.lower() for name in process_names}
        found = []
        for proc in psutil.process_iter(["name"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if name in wanted:
                    found.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return found
 
    def _close_processes(self, process_names: list[str], display_name: str) -> dict[str, Any]:
        processes = self._find_processes(process_names)
        if not processes:
            return {"ok": False, "message": f"{display_name} не запущен(а)."}
 
        closed, denied = [], []
        for proc in processes:
            try:
                proc.terminate()
            except psutil.AccessDenied:
                denied.append(proc)
            except psutil.NoSuchProcess:
                continue
 
        # Даём процессам немного времени на штатное завершение, и только
        # тем, кто не закрылся сам, посылаем принудительное завершение.
        gone, alive = psutil.wait_procs(
            [p for p in processes if p not in denied], timeout=3
        )
        closed.extend(gone)
        for proc in alive:
            try:
                proc.kill()
                closed.append(proc)
            except psutil.AccessDenied:
                denied.append(proc)
            except psutil.NoSuchProcess:
                continue
 
        if denied and not closed:
            return {
                "ok": False,
                "message": (
                    f"Не могу закрыть {display_name.lower()} — недостаточно прав. "
                    "Обычно так бывает, если приложение запущено с правами "
                    "администратора или как защищённое системой приложение "
                    "(например, из Microsoft Store) — Джарвису для этого "
                    "тоже нужны повышенные права."
                ),
            }
        if denied:
            return {
                "ok": True,
                "message": f"{display_name} закрыт(а) частично — часть процессов не поддалась (недостаточно прав).",
            }
        return {"ok": True, "message": f"{display_name} закрыт(а)."}
 
    def execute(self, match: CommandMatch) -> dict[str, Any]:
        command = match.command
        command_type = command.get("type", "python")
        slots = match.result.slots
 
        try:
            if command_type == "notepad":
                subprocess.Popen(["notepad.exe"], **_POPEN_KWARGS)
                message = "Блокнот успешно открыт."
            elif command_type == "calculator":
                subprocess.Popen(["calc.exe"], **_POPEN_KWARGS)
                message = "Калькулятор успешно открыт."
            elif command_type == "close_app":
                process_names = command.get("process_names", [])
                if not process_names:
                    return {"ok": False, "message": "Не указаны имена процессов для закрытия."}
                display_name = command.get("display_name", command.get("id", "Приложение"))
                result = self._close_processes(process_names, display_name)
                return {
                    "ok": result["ok"],
                    "command_id": command.get("id"),
                    "confidence": match.result.confidence,
                    "message": result["message"],
                }
            elif command_type == "app":
                uri = command.get("uri")
                executable = command.get("executable", "")
 
                if uri:
                    if not self._protocol_registered(uri):
                        fallback_url = command.get("fallback_url")
                        if fallback_url:
                            webbrowser.open(fallback_url)
                            message = command.get(
                                "missing_message",
                                "Приложение не установлено. Открыл веб-версию.",
                            )
                        else:
                            return {
                                "ok": False,
                                "command_id": command.get("id"),
                                "message": command.get(
                                    "missing_message",
                                    "Приложение не установлено.",
                                ),
                            }
                    else:
                        os.startfile(uri)
                        message = command.get("success_message", "Приложение открыто.")
                elif executable:
                    if not self._executable_exists(executable):
                        fallback_url = command.get("fallback_url")
                        if fallback_url:
                            webbrowser.open(fallback_url)
                            message = command.get(
                                "missing_message",
                                "Приложение не установлено. Открыл веб-версию.",
                            )
                        else:
                            return {
                                "ok": False,
                                "command_id": command.get("id"),
                                "message": command.get(
                                    "missing_message",
                                    f"Не найдено приложение: {executable}",
                                ),
                            }
                    else:
                        args = command.get("args")
                        subprocess.Popen(
                            args if isinstance(args, list) and args else [executable],
                            **_POPEN_KWARGS,
                        )
                        message = command.get("success_message", "Приложение открыто.")
                else:
                    return {"ok": False, "message": "Не указано приложение."}
            elif command_type == "browser":
                url = slots.get("url") or command.get("url") or "https://www.google.com"
                if not str(url).startswith(("http://", "https://")):
                    url = "https://" + str(url)
                webbrowser.open(str(url))
                message = "Сайт открыт."
            elif command_type == "search":
                query = slots.get("query", "").strip()
                if not query:
                    return {"ok": False, "message": "Не найден поисковый запрос."}
                engine = command.get("engine", "google")
                if engine == "youtube":
                    url = "https://www.youtube.com/results?search_query=" + quote(query)
                else:
                    url = "https://www.google.com/search?q=" + quote(query)
                webbrowser.open(url)
                message = f"Ищу: {query}"
            elif command_type == "path":
                path = slots.get("path") or command.get("path", "")
                path = os.path.expandvars(os.path.expanduser(str(path))).strip()
                if not path:
                    return {"ok": False, "message": "Не указан путь."}
                if not os.path.exists(path):
                    return {"ok": False, "message": f"Путь не найден: {path}"}
                os.startfile(path)
                message = "Путь открыт."
            elif command_type == "cli":
                cmd = command.get("command", "")
                if not cmd:
                    return {"ok": False, "message": "Пустая команда."}
                subprocess.Popen(cmd, shell=True, **_POPEN_KWARGS)
                message = "Команда запущена."
            else:
                return {"ok": False, "message": f"Неизвестный тип команды: {command_type}"}
        except Exception as e:
            print(f"[Commands] Ошибка {command.get('id')}: {e}")
            return {"ok": False, "command_id": command.get("id"), "message": str(e)}
 
        return {
            "ok": True,
            "command_id": command.get("id"),
            "confidence": match.result.confidence,
            "message": message,
        }
 
 
_manager = CommandManager()
 
 
def reload_commands() -> None:
    _manager.reload()
 
 
def match_local_command(text: str) -> CommandMatch | None:
    return _manager.match(text)
 
 
def get_command_grammar_phrases() -> list[str]:
    """Список всех фраз команд — для грамматически-ограниченного
    распознавания Vosk (см. jarvis_voice.listen)."""
    return _manager.all_phrases()
 
 
def execute_local_command(match: CommandMatch) -> dict[str, Any]:
    return _manager.execute(match)
