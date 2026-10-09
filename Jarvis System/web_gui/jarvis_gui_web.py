"""Современный GUI JARVIS на HTML/CSS/JS поверх pywebview.

Заменяет jarvis_gui.py (customtkinter). Вся логика голосового движка,
команд и настроек не тронута — это по-прежнему jarvis_core / jarvis_voice /
jarvis_tts / jarvis_memory / jarvis_settings. Этот модуль отвечает только
за то, чтобы:
  1) поднять окно pywebview с www/index.html;
  2) прокинуть в JS вызовы (JarvisWebApi — это js_api для pywebview,
     методы доступны в браузере как `pywebview.api.<имя>(...)`);
  3) пушить события из Python в JS через window.evaluate_js(...), когда
     меняется состояние (idle/listening/thinking/speaking/error), уровень
     микрофона/TTS, лог, тосты, индикаторы сети и т.д.

Запуск: python jarvis_gui_web.py (из "Jarvis System/web_gui/", либо через
установщик/ярлык, который должен указывать сюда вместо jarvis_gui.py).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time

import webview
from PIL import Image, ImageDraw
from pystray import Icon, Menu, MenuItem

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # "Jarvis System"

import jarvis_core
import jarvis_tts
import jarvis_voice
from jarvis_memory import add_note, add_reminder, delete_note_by_id, load_notes, load_reminders, start_reminder_scheduler
from jarvis_network import is_online
from jarvis_paths import PROJECT_DIR
from jarvis_settings import (
    SILERO_SPEAKERS,
    TTS_ENGINES,
    get_elevenlabs_api_key,
    get_groq_api_key,
    load_settings,
    save_settings,
)

WWW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "www")

PERFORMANCE_MODES = {
    "performance": "Производительный",
    "balanced": "Сбалансированный",
    "economy": "Экономичный",
}

MASK = "•" * 16


def _build_tray_image() -> Image.Image:
    """Иконка для системного трея, без внешних файлов — просто тёмный
    кружок с акцентной точкой в тон интерфейсу (та же пара цветов, что у
    орба на странице "Система")."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((2, 2, size - 2, size - 2), fill=(22, 47, 73, 255))
    pad = size * 0.28
    draw.ellipse((pad, pad, size - pad, size - pad), fill=(74, 168, 255, 255))
    return img


class JarvisWebApi:
    """js_api для pywebview: каждый публичный метод доступен в JS как
    `pywebview.api.<snake_case_имя>(...)` и возвращает Promise."""

    def __init__(self):
        self.window: webview.Window | None = None
        self.settings = load_settings()
        self.models_ready = False
        self._models_loading = False
        self.wake_detector = None
        self._wake_running = False
        self.reminder_stop = None
        self._speaking_stop = threading.Event()
        self.tray_icon: Icon | None = None
        self._quitting = False

    # ------------------------------------------------------------------ #
    # Инфраструктура: связь с окном, пуш событий в JS
    # ------------------------------------------------------------------ #
    def set_window(self, window: webview.Window) -> None:
        self.window = window

    def _js(self, script: str) -> None:
        if self.window is None:
            return
        try:
            self.window.evaluate_js(script)
        except Exception as exc:
            print(f"[WebGUI] evaluate_js: {exc}")

    def _push_state(self, state: str, label: str | None = None) -> None:
        self._js(f"window.jarvisSetState({json.dumps(state)}, {json.dumps(label)})")

    def _push_status_text(self, text: str) -> None:
        self._js(f"window.jarvisSetStatusText({json.dumps(text)})")

    def _push_log(self, author: str, text: str) -> None:
        self._js(f"window.jarvisLogAdd({json.dumps(author)}, {json.dumps(text)})")

    def _push_toast(self, text: str) -> None:
        self._js(f"window.jarvisToast({json.dumps(text)})")

    def _push_dot(self, key: str, value: bool) -> None:
        self._js(f"window.jarvisSetDot({json.dumps(key)}, {json.dumps(bool(value))})")

    def _push_net(self, online: bool) -> None:
        self._js(f"window.jarvisSetNet({json.dumps(bool(online))})")

    def _push_mic_enabled(self, enabled: bool) -> None:
        self._js(f"window.jarvisSetMicEnabled({json.dumps(bool(enabled))})")

    def _push_mic_level(self, level: float) -> None:
        self._js(f"window.jarvisOnLevel({level:.4f})")

    def _push_tts_level(self, level: float) -> None:
        self._js(f"window.jarvisOnTtsLevel({level:.4f})")

    def _push_notes(self) -> None:
        self._js(f"window.jarvisSetNotes({json.dumps(load_notes())})")

    def _push_reminders(self) -> None:
        self._js(f"window.jarvisSetReminders({json.dumps(load_reminders())})")

    def _push_reminder_popup(self, text: str) -> None:
        self._js(f"window.jarvisReminderPopup({json.dumps(text)})")

    # ------------------------------------------------------------------ #
    # Загрузка начального состояния (вызывается из JS один раз при старте)
    # ------------------------------------------------------------------ #
    def get_bootstrap(self) -> dict:
        settings = self.settings
        return {
            "settings": {
                "performance_mode": settings.get("performance_mode", "balanced"),
                "groq_model": settings.get("groq_model", "openai/gpt-oss-120b"),
                "tts_engine": settings.get("tts_engine", "coqui"),
                "xtts_speaker_wav": settings.get("xtts_speaker_wav", "resources/tts/jarvis_voice.wav"),
                "xtts_device": settings.get("xtts_device", "cpu"),
                "xtts_language": settings.get("xtts_language", "ru"),
                "xtts_split_sentences": bool(settings.get("xtts_split_sentences", True)),
                "elevenlabs_voice_id": settings.get("elevenlabs_voice_id", ""),
                "elevenlabs_model": settings.get("elevenlabs_model", "eleven_multilingual_v2"),
                "silero_speaker": settings.get("silero_speaker", "eugene"),
                "silero_device": settings.get("silero_device", "cpu"),
                "silero_sample_rate": settings.get("silero_sample_rate", 48000),
                "wake_word_enabled": bool(settings.get("wake_word_enabled", True)),
            },
            "groq_key_set": bool(get_groq_api_key(settings)),
            "eleven_key_set": bool(get_elevenlabs_api_key(settings)),
            "performance_modes": PERFORMANCE_MODES,
            "tts_engines": TTS_ENGINES,
            "silero_speakers": SILERO_SPEAKERS,
            "notes": load_notes(),
            "reminders": load_reminders(),
        }

    def on_ready(self) -> bool:
        """Вызывается из JS после того, как все window.jarvisXxx колбэки
        уже определены — аналог конца JarvisApp.__init__ в tkinter-версии.

        Раньше часть этой логики (в первую очередь is_online(), у которой
        таймаут до ~2.4 сек на двух пробах) выполнялась синхронно внутри
        самого js_api-вызова. На части бэкендов pywebview такие вызовы
        обрабатываются в том же потоке, что рисует окно — из-за этого при
        открытии программы окно на пару секунд подвисало. Теперь метод
        только запускает фоновый поток и сразу возвращает управление в JS."""
        threading.Thread(target=self._on_ready_worker, daemon=True).start()
        return True

    def _on_ready_worker(self) -> None:
        if self.reminder_stop is None:
            self.reminder_stop = start_reminder_scheduler(self._on_reminder)
        self._push_dot("local", True)
        self._push_dot("groq", bool(get_groq_api_key(self.settings)))
        self._push_dot("xtts", jarvis_tts.is_configured())
        self._push_net(bool(is_online()))
        threading.Thread(target=self._network_loop, daemon=True).start()
        if self.settings.get("wake_word_enabled"):
            self._start_model_load()
        else:
            self._push_status_text(
                "Готов. Печатайте команды или нажмите на микрофон — "
                "голосовые модели загрузятся при первом использовании."
            )
            self._push_state("idle", "ГОТОВ (ТЕКСТ)")

    def _network_loop(self) -> None:
        while True:
            try:
                self._push_net(bool(is_online()))
            except Exception:
                pass
            time.sleep(8)

    # ------------------------------------------------------------------ #
    # Загрузка голосовых моделей / wake word
    # ------------------------------------------------------------------ #
    def _load_models(self) -> None:
        if self._models_loading or self.models_ready:
            return
        self._models_loading = True
        try:
            self._push_status_text("Загрузка GigaAM и VAD...")
            self._push_state("thinking", "ЗАГРУЗКА")
            jarvis_voice.warmup_voice_models()
            self._push_dot("gigaAM", True)
            self._push_dot("local", True)
            self._push_dot("groq", bool(get_groq_api_key(self.settings)))
            self._push_dot("xtts", jarvis_tts.is_configured())
            self._push_mic_enabled(True)
            self.models_ready = True
            self._push_status_text("Система готова к работе")
            self._push_state("idle")
            try:
                jarvis_voice.play_sound(jarvis_voice.SOUND_RUN)
            except Exception:
                pass
            if self.settings.get("wake_word_enabled"):
                self._start_wake()
        except Exception as exc:
            print(f"[JARVIS] Ошибка запуска: {exc}")
            self._push_status_text("Ошибка загрузки компонентов")
            self._push_state("error")
            self._push_dot("gigaAM", False)
        finally:
            self._models_loading = False

    def _start_model_load(self) -> None:
        if self._models_loading or self.models_ready:
            return
        threading.Thread(target=self._load_models, daemon=True).start()

    def _resolve_path(self, value: str) -> str:
        return value if os.path.isabs(value) else os.path.join(str(PROJECT_DIR), value)

    def _start_wake(self) -> None:
        if self.wake_detector is not None or not self.models_ready:
            return
        try:
            from jarvis_wakeword import RustpotterWakeWordDetector

            cli = self._resolve_path(self.settings.get("rustpotter_cli_path", "resources/rustpotter/rustpotter-cli_win_x86_64.exe"))
            model = self._resolve_path(self.settings.get("rustpotter_model_path", "resources/rustpotter/jarvis-ru.rpw"))
            self.wake_detector = RustpotterWakeWordDetector(
                on_wake=self._wake_detect,
                cli_path=cli,
                model_path=model,
                threshold=float(self.settings.get("wake_word_threshold", 0.5)),
                device_index=int(self.settings.get("rustpotter_device_index", 0)),
            )
            self.wake_detector.start()
            self._push_dot("wake", True)
        except Exception as exc:
            print(f"[WakeWord] {exc}")
            self._push_dot("wake", False)

    def _stop_wake(self) -> None:
        detector = self.wake_detector
        self.wake_detector = None
        if detector is not None:
            try:
                detector.stop()
            except Exception as exc:
                print(f"[WakeWord] stop: {exc}")
        self._push_dot("wake", False)

    def _wake_detect(self) -> None:
        if self.models_ready and not self._wake_running:
            self._wake_running = True
            threading.Thread(target=self._voice_reply, daemon=True).start()

    # ------------------------------------------------------------------ #
    # Голос / текст / обработка
    # ------------------------------------------------------------------ #
    def _voice_reply(self) -> None:
        try:
            self._push_mic_enabled(False)
            self._stop_wake()
            # Раньше play_ack_sound() вызывался синхронно и блокировал
            # поток (sd.play()+sd.wait() внутри play_sound) до конца звука
            # подтверждения — то есть запись реально начиналась только
            # ПОСЛЕ того, как звук доигрывал, и всё сказанное сразу после
            # "Джарвис" терялось. Теперь звук проигрывается в фоне, а
            # jarvis_voice.listen() (открывает микрофон) запускается сразу
            # же, без ожидания — говорить можно хоть поверх звука.
            threading.Thread(target=self._play_ack_sound_safe, daemon=True).start()
            self._push_status_text("Слушаю...")
            self._push_state("listening")
            result = jarvis_voice.listen(on_level=self._push_mic_level)
            self._push_mic_level(0.0)
            self._push_state("thinking")
            self._push_status_text("Распознаю речь...")
            text = result.get("text", "")
            grammar = result.get("grammar_text")
            if text or grammar:
                self._process(text, grammar)
            else:
                self._push_state("idle")
        except Exception as exc:
            self._push_log("ОШИБКА", str(exc))
            self._push_state("error")
        finally:
            self._wake_running = False
            self._push_mic_enabled(self.models_ready)
            if self.models_ready and self.settings.get("wake_word_enabled"):
                self._start_wake()

    def _play_ack_sound_safe(self) -> None:
        try:
            jarvis_voice.play_ack_sound()
        except Exception:
            pass

    def _speak(self, text: str) -> None:
        self._push_state("speaking")
        self._speaking_stop.clear()
        level_thread = threading.Thread(target=self._tts_level_loop, daemon=True)
        level_thread.start()
        try:
            jarvis_tts.speak(text)
        finally:
            self._speaking_stop.set()
            level_thread.join(timeout=1.0)
            self._push_tts_level(0.0)
            self._push_state("idle")

    def _tts_level_loop(self) -> None:
        # Аналог _sample_tts_level() из tkinter-версии: читает уже
        # посчитанный буфер воспроизведения, отдельного аудиопотока не надо.
        while not self._speaking_stop.is_set():
            try:
                info = jarvis_tts.get_now_playing()
                audio = info.get("audio")
                samplerate = info.get("samplerate")
                if audio is not None and samplerate:
                    import numpy as np

                    elapsed = time.monotonic() - info["started_at"]
                    idx = int(elapsed * samplerate)
                    half_window = max(1, samplerate // 40)
                    start = max(0, idx - half_window)
                    end = min(len(audio), idx + half_window)
                    if start < end:
                        level = float(np.sqrt(np.mean(np.square(audio[start:end]))))
                        self._push_tts_level(min(1.0, level * 6.0))
            except Exception:
                pass
            time.sleep(0.09)

    def _process(self, text: str, grammar: str | None = None) -> None:
        try:
            self._push_status_text("Обрабатываю запрос...")
            self._push_state("thinking")
            result = jarvis_core.process_message(text, grammar_text=grammar, on_speak_ready=lambda value: self._speak(value))
            self._push_log("ВЫ", text)
            self._push_log("JARVIS", result.get("text", ""))
            if result.get("type") == "sound":
                jarvis_voice.play_sound(result["path"])
            elif result.get("type") == "local":
                jarvis_voice.play_random_ok()
            elif result.get("type") != "streamed":
                self._speak(result.get("text", ""))
        except Exception as exc:
            self._push_status_text("Ошибка")
            self._push_log("ОШИБКА", str(exc))
            self._push_state("error")
        finally:
            self._push_status_text("Система готова к работе")
            self._push_mic_enabled(self.models_ready)
            self._push_reminders()
            self._push_state("idle")

    # ------------------------------------------------------------------ #
    # Методы, вызываемые из JS (pywebview.api.*)
    # ------------------------------------------------------------------ #
    def send_text(self, text: str) -> None:
        text = (text or "").strip()
        if text:
            threading.Thread(target=self._process, args=(text,), daemon=True).start()

    def mic_input(self) -> None:
        if self.models_ready:
            threading.Thread(target=self._voice_reply, daemon=True).start()
        elif not self._models_loading:
            def _load_then_listen():
                self._push_mic_enabled(False)
                self._load_models()
                if self.models_ready:
                    self._voice_reply()
                else:
                    self._push_mic_enabled(False)
            threading.Thread(target=_load_then_listen, daemon=True).start()

    def add_note_api(self, text: str) -> dict:
        text = (text or "").strip()
        if not text:
            return {"ok": False}
        try:
            add_note(text)
            self._push_notes()
            self._push_log("JARVIS", f"Заметка сохранена: {text}")
            return {"ok": True}
        except Exception as exc:
            self._push_log("ОШИБКА", str(exc))
            return {"ok": False, "error": str(exc)}

    def delete_note_api(self, note_id: str) -> dict:
        try:
            removed = delete_note_by_id(note_id)
        except Exception as exc:
            self._push_log("ОШИБКА", str(exc))
            return {"ok": False, "error": str(exc)}
        if removed is None:
            return {"ok": False}
        self._push_notes()
        self._push_log("JARVIS", f"Заметка удалена: {removed.get('text', '')}")
        return {"ok": True}

    def add_reminder_api(self, text: str, when: str) -> dict:
        text = (text or "").strip()
        when = (when or "").strip()
        if not text or not when:
            return {"ok": False}
        try:
            reminder = add_reminder(text, when)
            self._push_reminders()
            self._push_log("JARVIS", f"Напоминание поставлено: {reminder['text']}")
            return {"ok": True}
        except Exception as exc:
            self._push_log("ОШИБКА", str(exc))
            return {"ok": False, "error": str(exc)}

    def _on_reminder(self, reminder: dict) -> None:
        text = reminder.get("text", "")
        self._push_reminders()
        self._push_reminder_popup(text)
        self._push_log("НАПОМИНАНИЕ", text)
        threading.Thread(target=self._speak_reminder, args=(text,), daemon=True).start()

    def _speak_reminder(self, text: str) -> None:
        try:
            jarvis_tts.speak(f"Напоминание. {text}")
        except Exception as exc:
            print(f"[Reminders] Ошибка озвучки: {exc}")

    def save_settings_api(self, payload: dict) -> dict:
        payload = payload or {}
        groq_value = str(payload.get("groq_api_key", "")).strip()
        if groq_value and groq_value != MASK:
            self.settings["groq_api_key"] = groq_value
        eleven_value = str(payload.get("elevenlabs_api_key", "")).strip()
        if eleven_value and eleven_value != MASK:
            self.settings["elevenlabs_api_key"] = eleven_value

        self.settings.update({
            "performance_mode": payload.get("performance_mode", self.settings.get("performance_mode", "balanced")),
            "groq_model": str(payload.get("groq_model", "")).strip() or "openai/gpt-oss-120b",
            "tts_engine": payload.get("tts_engine", self.settings.get("tts_engine", "coqui")),
            "xtts_speaker_wav": str(payload.get("xtts_speaker_wav", "")).strip(),
            "xtts_device": payload.get("xtts_device", "cpu"),
            "xtts_language": str(payload.get("xtts_language", "")).strip() or "ru",
            "xtts_split_sentences": bool(payload.get("xtts_split_sentences", True)),
            "elevenlabs_voice_id": str(payload.get("elevenlabs_voice_id", "")).strip(),
            "elevenlabs_model": payload.get("elevenlabs_model", "eleven_multilingual_v2"),
            "silero_speaker": payload.get("silero_speaker", "eugene"),
            "silero_device": payload.get("silero_device", "cpu"),
            "silero_sample_rate": int(payload.get("silero_sample_rate", 48000)),
            "wake_word_enabled": bool(payload.get("wake_word_enabled", True)),
        })
        save_settings(self.settings)
        jarvis_core.set_groq_model(self.settings["groq_model"])
        jarvis_core.reset_groq_client()
        self._push_toast("✓  Настройки сохранены")
        self._push_dot("groq", bool(get_groq_api_key(self.settings)))
        self._push_dot("xtts", jarvis_tts.is_configured())
        if self.settings["wake_word_enabled"]:
            if self.models_ready:
                self._start_wake()
            else:
                self._start_model_load()
        else:
            self._stop_wake()
        return {"ok": True, "tts_engine_label": TTS_ENGINES.get(self.settings["tts_engine"], "Coqui XTTS-v2")}

    def on_close(self) -> bool | None:
        """Обработчик window.events.closing (крестик окна).

        По умолчанию закрытие окна сворачивает JARVIS в трей вместо
        завершения: окно прячется, а голосовой движок (в т.ч. wake word)
        продолжает работать в фоне. Настоящий выход — только через пункт
        "Выход" в меню трея (см. _tray_exit), который сначала выставляет
        self._quitting = True.

        pywebview умеет отменять закрытие, если обработчик вернёт False
        (начиная с релиза 3.5) — этим и пользуемся. window.hide()
        запускаем в отдельном потоке: так делает вся практика связки
        pywebview+pystray, чтобы не поймать блокировку на некоторых
        бэкендах при вызове напрямую из обработчика события."""
        if self._quitting:
            return None
        self._ensure_tray()
        threading.Thread(target=self.window.hide, daemon=True).start()
        return False

    def _ensure_tray(self) -> None:
        if self.tray_icon is not None:
            return
        menu = Menu(
            MenuItem("Открыть JARVIS", self._tray_open, default=True),
            MenuItem("Выход", self._tray_exit),
        )
        self.tray_icon = Icon("jarvis", _build_tray_image(), title="JARVIS", menu=menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _tray_open(self, icon, item) -> None:
        if self.window is not None:
            threading.Thread(target=self.window.show, daemon=True).start()

    def _tray_exit(self, icon, item) -> None:
        self._quitting = True
        try:
            icon.stop()
        except Exception:
            pass
        self._on_close_worker()
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:
                pass

    def _on_close_worker(self) -> None:
        try:
            if self.reminder_stop is not None:
                self.reminder_stop.set()
        except Exception:
            pass
        try:
            self._stop_wake()
        except Exception as exc:
            print(f"[WebGUI] on_close stop_wake: {exc}")
        try:
            jarvis_voice.play_sound(jarvis_voice.SOUND_OFF)
        except Exception:
            pass


def main() -> None:
    # Косметические ошибки pywebview на связке WinForms/WebView2
    # (AccessibilityObject.Bounds recursion, "CoreWebView2Controller members
    # can only be accessed from the UI thread") не влияют на работу
    # приложения — это внутренние обращения самого pywebview к window.native,
    # а не что-то из нашего кода. Глушим уровень логирования, чтобы не
    # засорять консоль.
    logging.getLogger("pywebview").setLevel(logging.CRITICAL)

    api = JarvisWebApi()
    window = webview.create_window(
        "JARVIS — Local AI System",
        url=os.path.join(WWW_DIR, "index.html"),
        js_api=api,
        width=1180,
        height=760,
        min_size=(980, 680),
        background_color="#080c12",
    )
    api.set_window(window)
    window.events.closing += api.on_close
    api._ensure_tray()
    webview.start()


if __name__ == "__main__":
    main()
