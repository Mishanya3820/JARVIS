"""Rustpotter wake-word detector for JARVIS.

Rustpotter CLI owns the microphone while listening for the wake word.
After detection the GUI stops this process before starting Vosk, so both
systems never try to capture the microphone at the same time.
"""
from __future__ import annotations

import os
import re
import subprocess
import threading
import time


DETECTION_LINE_RE = re.compile(r"Wakeword detection:")
SCORE_RE = re.compile(r"(\w*score):\s*([\d.]+)")


class RustpotterWakeWordDetector:
    def __init__(
        self,
        on_wake,
        cli_path: str,
        model_path: str,
        threshold: float = 0.5,
        device_index: int | None = 0,
        cooldown_seconds: float = 2.0,
    ):
        self.on_wake = on_wake
        self.cli_path = cli_path
        self.model_path = model_path
        self.threshold = threshold
        self.device_index = device_index
        self.cooldown_seconds = cooldown_seconds
        self._process = None
        self._thread = None
        self._stop_event = threading.Event()
        self._last_trigger_time = 0.0

    @staticmethod
    def _resolve_project_path(path: str) -> str:
        if os.path.isabs(path):
            return path
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.normpath(os.path.join(project_dir, path))

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        process = self._process
        if process:
            try:
                process.terminate()
            except Exception:
                pass
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None
        self._process = None

    def _run(self) -> None:
        cli_path = self._resolve_project_path(self.cli_path)
        model_path = self._resolve_project_path(self.model_path)

        if not os.path.isfile(cli_path):
            print(f"[WakeWord/Rustpotter] CLI не найден: {cli_path}")
            return
        if not os.path.isfile(model_path):
            print(f"[WakeWord/Rustpotter] Модель .rpw не найдена: {model_path}")
            return

        cmd = [
            cli_path,
            "spot",
            "-t", str(self.threshold),
            "-e",
        ]

        if self.device_index is not None:
            cmd.extend(["--device-index", str(self.device_index)])

        cmd.append(model_path)

        print(f"[WakeWord/Rustpotter] Запускаю: {' '.join(cmd)}")

        try:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=creationflags,
            )
        except Exception as e:
            print(f"[WakeWord/Rustpotter] Ошибка запуска: {e}")
            return

        print("[WakeWord/Rustpotter] Слушаю в фоне...")

        try:
            for line in iter(self._process.stdout.readline, ""):
                if self._stop_event.is_set():
                    break

                line = line.strip()
                if not line or not DETECTION_LINE_RE.search(line):
                    continue

                score = self._extract_score(line)
                if score is None:
                    continue

                now = time.monotonic()
                if now - self._last_trigger_time <= self.cooldown_seconds:
                    continue

                self._last_trigger_time = now
                print(f"[WakeWord/Rustpotter] Обнаружено! score={score:.2f}")

                try:
                    self.on_wake()
                except Exception as e:
                    print(f"[WakeWord/Rustpotter] Ошибка обработчика: {e}")
        finally:
            try:
                self._process.stdout.close()
            except Exception:
                pass
            try:
                self._process.wait(timeout=1)
            except Exception:
                pass

    @staticmethod
    def _extract_score(line: str):
        for key, value in SCORE_RE.findall(line):
            if key == "score":
                try:
                    return float(value)
                except ValueError:
                    return None
        return None
