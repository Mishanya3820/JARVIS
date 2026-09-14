# Загрузчик и исполнитель локальных команд JARVIS.

from __future__ import annotations

import ctypes
import datetime
import json
import os
import shutil
import socket
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

_POPen_KWARGS: dict[str, Any] = {
    "stdout": subprocess.DEVNULL,
    "stderr": subprocess.DEVNULL,
    "stdin": subprocess.DEVNULL,
}
if os.name == "nt":
    _POPen_KWARGS["creationflags"] = subprocess.CREATE_NO_WINDOW


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
        phrases: list[str] = []
        for command in self.commands:
            phrases.extend(command.get("phrases", []))
        return phrases

    @staticmethod
    def _protocol_registered(uri: str) -> bool:
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
        gone, alive = psutil.wait_procs([p for p in processes if p not in denied], timeout=3)
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
            return {"ok": False, "message": f"Не могу закрыть {display_name.lower()} — недостаточно прав."}
        if denied:
            return {"ok": True, "message": f"{display_name} закрыт(а) частично — часть процессов не поддалась."}
        return {"ok": True, "message": f"{display_name} закрыт(а)."}

    @staticmethod
    def _windows_key_action(key: str, modifiers: tuple[int, ...] = ()) -> None:
        if os.name != "nt":
            raise RuntimeError("Управление окнами доступно только в Windows.")
        user32 = ctypes.windll.user32
        KEYEVENTF_KEYUP = 0x0002
        VK_LWIN = 0x5B
        vk = ord(key.upper()) if len(key) == 1 else key
        user32.keybd_event(VK_LWIN, 0, 0, 0)
        for modifier in modifiers:
            user32.keybd_event(modifier, 0, 0, 0)
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        for modifier in reversed(modifiers):
            user32.keybd_event(modifier, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)

    @staticmethod
    def _minimize_all_windows() -> str:
        CommandManager._windows_key_action("M")
        return "Все окна свернуты."

    @staticmethod
    def _restore_all_windows() -> str:
        CommandManager._windows_key_action("M", (0x10,))
        return "Окна восстановлены."

    @staticmethod
    def _minimize_windows(process_names: list[str], display_name: str) -> str:
        """Сворачивает окна выбранного приложения через WinAPI."""
        if os.name != "nt":
            return "Управление окнами доступно только в Windows."

        user32 = ctypes.windll.user32
        EnumWindows = user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        GetWindowThreadProcessId = user32.GetWindowThreadProcessId
        IsWindowVisible = user32.IsWindowVisible
        ShowWindow = user32.ShowWindow
        SW_MINIMIZE = 6

        wanted = {name.lower() for name in process_names}
        matches: list[int] = []

        @EnumWindowsProc
        def callback(hwnd, _lparam):
            if not IsWindowVisible(hwnd):
                return True
            pid = ctypes.c_ulong()
            GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                proc_name = (psutil.Process(pid.value).name() or "").lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return True
            if proc_name in wanted:
                matches.append(int(hwnd))
            return True

        EnumWindows(callback, 0)
        if not matches:
            return f"Окно {display_name} не найдено."

        for hwnd in matches:
            ShowWindow(hwnd, SW_MINIMIZE)
        return f"{display_name} свернут(а)."

    @staticmethod
    def _minimize_current_window() -> str:
        """Сворачивает текущее активное окно без PowerShell/SendKeys."""
        if os.name != "nt":
            return "Управление окнами доступно только в Windows."

        user32 = ctypes.windll.user32
        GetForegroundWindow = user32.GetForegroundWindow
        ShowWindow = user32.ShowWindow
        SW_MINIMIZE = 6
        hwnd = GetForegroundWindow()
        if not hwnd:
            return "Активное окно не найдено."
        ShowWindow(hwnd, SW_MINIMIZE)
        return "Текущее окно свернуто."

    @staticmethod
    def _restore_windows(process_names: list[str], display_name: str) -> str:
        if os.name != "nt":
            return "Управление окнами доступно только в Windows."

        user32 = ctypes.windll.user32
        EnumWindows = user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        GetWindowThreadProcessId = user32.GetWindowThreadProcessId
        IsWindowVisible = user32.IsWindowVisible
        ShowWindow = user32.ShowWindow
        SetForegroundWindow = user32.SetForegroundWindow
        SW_RESTORE = 9

        wanted = {name.lower() for name in process_names}
        matches: list[int] = []

        @EnumWindowsProc
        def callback(hwnd, _lparam):
            if not IsWindowVisible(hwnd):
                return True
            pid = ctypes.c_ulong()
            GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                proc_name = (psutil.Process(pid.value).name() or "").lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return True
            if proc_name in wanted:
                matches.append(int(hwnd))
            return True

        EnumWindows(callback, 0)
        if not matches:
            return f"Окно {display_name} не найдено."

        for hwnd in matches:
            ShowWindow(hwnd, SW_RESTORE)
        SetForegroundWindow(matches[-1])
        return f"{display_name} развернут(а)."

    @staticmethod
    def _system_status() -> str:
        cpu = psutil.cpu_percent(interval=0.4)
        memory = psutil.virtual_memory()
        drive = os.environ.get("SystemDrive", "C:")
        try:
            disk = psutil.disk_usage(drive + "\\")
            disk_text = f"Диск {drive}: свободно {disk.free / (1024 ** 3):.1f} ГБ из {disk.total / (1024 ** 3):.1f} ГБ"
        except OSError:
            disk_text = "Свободное место системного диска недоступно."
        battery = psutil.sensors_battery()
        battery_text = "Питание: от сети"
        if battery is not None:
            state = "заряжается" if battery.power_plugged and battery.percent < 100 else ("от сети" if battery.power_plugged else "от батареи")
            battery_text = f"Батарея: {battery.percent:.0f}% ({state})"
        uptime = datetime.datetime.now() - datetime.datetime.fromtimestamp(psutil.boot_time())
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        days, hours = divmod(hours, 24)
        uptime_text = f"Аптайм: {days} дн. {hours} ч. {remainder // 60} мин."
        return (
            f"Процессор: {cpu:.0f}%\n"
            f"ОЗУ: {memory.percent:.0f}% занято ({memory.used / (1024 ** 3):.1f} ГБ из {memory.total / (1024 ** 3):.1f} ГБ)\n"
            f"{disk_text}\n{battery_text}\n{uptime_text}"
        )

    @staticmethod
    def _network_status() -> str:
        hostname = socket.gethostname()
        addresses: list[str] = []
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            address = info[4][0]
            if address != "127.0.0.1" and address not in addresses:
                addresses.append(address)
        sent = psutil.net_io_counters().bytes_sent / (1024 ** 3)
        received = psutil.net_io_counters().bytes_recv / (1024 ** 3)
        address_text = ", ".join(addresses) if addresses else "локальный интерфейс не определён"
        return f"Имя компьютера: {hostname}\nЛокальный IP: {address_text}\nПередано: {sent:.2f} ГБ\nПолучено: {received:.2f} ГБ"

    def execute(self, match: CommandMatch) -> dict[str, Any]:
        command = match.command
        command_type = command.get("type", "python")
        slots = match.result.slots
        try:
            if command_type == "notepad":
                subprocess.Popen(["notepad.exe"], **_POPen_KWARGS)
                message = "Блокнот успешно открыт."
            elif command_type == "calculator":
                subprocess.Popen(["calc.exe"], **_POPen_KWARGS)
                message = "Калькулятор успешно открыт."
            elif command_type == "system_status":
                message = self._system_status()
            elif command_type == "network_status":
                message = self._network_status()
            elif command_type == "time":
                message = f"Сейчас {datetime.datetime.now().strftime('%H:%M')}."
            elif command_type == "minimize_all":
                message = self._minimize_all_windows()
            elif command_type == "restore_all":
                message = self._restore_all_windows()
            elif command_type == "minimize_current":
                message = self._minimize_current_window()
            elif command_type == "minimize_window":
                process_names = command.get("process_names", [])
                if not process_names:
                    return {"ok": False, "message": "Не указаны процессы для сворачивания окна."}
                display_name = command.get("display_name", command.get("id", "Приложение"))
                message = self._minimize_windows(process_names, display_name)
                return {"ok": "не найдено" not in message.lower(), "command_id": command.get("id"), "confidence": match.result.confidence, "message": message}
            elif command_type == "restore_window":
                process_names = command.get("process_names", [])
                if not process_names:
                    return {"ok": False, "message": "Не указаны процессы для восстановления окна."}
                display_name = command.get("display_name", command.get("id", "Приложение"))
                message = self._restore_windows(process_names, display_name)
                return {"ok": "не найдено" not in message.lower(), "command_id": command.get("id"), "confidence": match.result.confidence, "message": message}
            elif command_type == "close_app":
                process_names = command.get("process_names", [])
                if not process_names:
                    return {"ok": False, "message": "Не указаны имена процессов для закрытия."}
                display_name = command.get("display_name", command.get("id", "Приложение"))
                result = self._close_processes(process_names, display_name)
                return {"ok": result["ok"], "command_id": command.get("id"), "confidence": match.result.confidence, "message": result["message"]}
            elif command_type == "app":
                uri = command.get("uri")
                executable = command.get("executable", "")
                if uri:
                    if not self._protocol_registered(uri):
                        fallback_url = command.get("fallback_url")
                        if fallback_url:
                            webbrowser.open(fallback_url)
                            message = command.get("missing_message", "Приложение не установлено. Открыл веб-версию.")
                        else:
                            return {"ok": False, "command_id": command.get("id"), "message": command.get("missing_message", "Приложение не установлено.")}
                    else:
                        os.startfile(uri)
                        message = command.get("success_message", "Приложение открыто.")
                elif executable:
                    if not self._executable_exists(executable):
                        fallback_url = command.get("fallback_url")
                        if fallback_url:
                            webbrowser.open(fallback_url)
                            message = command.get("missing_message", "Приложение не установлено. Открыл веб-версию.")
                        else:
                            return {"ok": False, "command_id": command.get("id"), "message": command.get("missing_message", f"Не найдено приложение: {executable}")}
                    else:
                        args = command.get("args")
                        subprocess.Popen(args if isinstance(args, list) and args else [executable], **_POPen_KWARGS)
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
                url = ("https://www.youtube.com/results?search_query=" if engine == "youtube" else "https://www.google.com/search?q=") + quote(query)
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
                subprocess.Popen(cmd, shell=True, **_POPen_KWARGS)
                message = "Команда запущена."
            else:
                return {"ok": False, "message": f"Неизвестный тип команды: {command_type}"}
        except Exception as e:
            print(f"[Commands] Ошибка {command.get('id')}: {e}")
            return {"ok": False, "command_id": command.get("id"), "message": str(e)}
        return {"ok": True, "command_id": command.get("id"), "confidence": match.result.confidence, "message": message}


_manager = CommandManager()


def reload_commands() -> None:
    _manager.reload()


def match_local_command(text: str) -> CommandMatch | None:
    return _manager.match(text)


def get_command_grammar_phrases() -> list[str]:
    return _manager.all_phrases()


def execute_local_command(match: CommandMatch) -> dict[str, Any]:
    return _manager.execute(match)
