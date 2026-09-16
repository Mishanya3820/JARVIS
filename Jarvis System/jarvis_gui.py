from __future__ import annotations

import os
import threading
import tkinter as tk

import customtkinter as ctk

import jarvis_core
import jarvis_tts
import jarvis_voice
from jarvis_memory import add_note, add_reminder, delete_note, format_notes, format_reminders, load_notes, load_reminders, start_reminder_scheduler
from jarvis_network import is_online
from jarvis_paths import PROJECT_DIR
from jarvis_settings import get_elevenlabs_api_key, get_groq_api_key, load_settings, save_settings

BG = "#080c12"
SIDEBAR = "#0d131b"
PANEL = "#111923"
PANEL_2 = "#151f2b"
PANEL_3 = "#192535"
FIELD = "#121b26"
BORDER = "#243244"
ACCENT = "#4aa8ff"
ACCENT_SOFT = "#1b3652"
TEXT = "#e7edf5"
TEXT_2 = "#b5c0ce"
MUTED = "#718096"
GOOD = "#62d391"
WARN = "#e5b85c"
BAD = "#ef7373"

MODES = {
    "performance": ("Производительный", "Максимальная скорость"),
    "balanced": ("Сбалансированный", "Рекомендуемый баланс"),
    "economy": ("Экономичный", "Минимальная нагрузка"),
}
ENGINES = {"coqui": "Coqui XTTS-v2", "elevenlabs": "ElevenLabs", "silero": "Silero TTS"}
SILERO_SPEAKERS = {
    "eugene": "Евгений — мужской, глубокий",
    "aidar": "Айдар — мужской",
    "baya": "Бая — женский",
    "kseniya": "Ксения — женский",
    "xenia": "Ксения — вариант",
}


class JarvisApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("JARVIS — Local AI System")
        self.geometry("1180x760")
        self.minsize(980, 680)
        self.configure(fg_color=BG)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.settings = load_settings()
        self.models_ready = False
        self.wake_detector = None
        self._wake_running = False
        self._anim_step = 0
        self._pages: dict[str, ctk.CTkFrame] = {}
        self.reminder_stop = start_reminder_scheduler(self._on_reminder)

        self._build_ui()
        self._update_network()
        threading.Thread(target=self.load_models, daemon=True).start()
        self.animate()

    def _font(self, size=12, weight="normal"):
        return ctk.CTkFont(size=size, weight=weight)

    def _card(self, parent, **kwargs):
        return ctk.CTkFrame(parent, fg_color=kwargs.pop("fg_color", PANEL), corner_radius=16, border_width=1, border_color=kwargs.pop("border_color", BORDER), **kwargs)

    def _label(self, parent, text, size=12, color=TEXT_2, weight="normal", **kwargs):
        return ctk.CTkLabel(parent, text=text, text_color=color, font=self._font(size, weight), **kwargs)

    def _field(self, parent, **kwargs):
        kwargs.setdefault("height", 42)
        kwargs.setdefault("corner_radius", 10)
        kwargs.setdefault("fg_color", FIELD)
        kwargs.setdefault("border_color", BORDER)
        kwargs.setdefault("text_color", TEXT)
        kwargs.setdefault("placeholder_text_color", MUTED)
        return ctk.CTkEntry(parent, **kwargs)

    def _option(self, parent, variable, values, width=210, command=None):
        """Единый тёмный стиль для всех выпадающих списков."""
        return ctk.CTkOptionMenu(
            parent,
            variable=variable,
            values=values,
            width=width,
            height=40,
            corner_radius=10,
            fg_color=ACCENT_SOFT,
            button_color=ACCENT,
            button_hover_color="#68b7ff",
            dropdown_fg_color=PANEL_2,
            dropdown_hover_color=ACCENT_SOFT,
            dropdown_text_color=TEXT,
            dropdown_font=self._font(12),
            text_color=TEXT,
            font=self._font(12),
            command=command,
        )

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.sidebar = ctk.CTkFrame(self, width=238, corner_radius=0, fg_color=SIDEBAR)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self._label(self.sidebar, "JARVIS", 29, TEXT, "bold").pack(anchor="w", padx=24, pady=(30, 0))
        self._label(self.sidebar, "LOCAL INTELLIGENCE", 10, ACCENT, "bold").pack(anchor="w", padx=25, pady=(1, 24))
        self.nav_system = self._nav_button("⌂", "Система", lambda: self.show_page("system"))
        self.nav_notes = self._nav_button("▤", "Заметки", lambda: self.show_page("notes"))
        self.nav_reminders = self._nav_button("◷", "Напоминания", lambda: self.show_page("reminders"))
        self.nav_settings = self._nav_button("⚙", "Настройки", lambda: self.show_page("settings"))
        ctk.CTkFrame(self.sidebar, height=1, fg_color=BORDER).pack(fill="x", padx=22, pady=20)
        self._label(self.sidebar, "СОСТОЯНИЕ СИСТЕМЫ", 10, MUTED, "bold").pack(anchor="w", padx=24, pady=(0, 10))
        self.dots = {}
        for key, name in (("gigaAM", "GigaAM STT"), ("wake", "Wake word"), ("local", "Local commands"), ("groq", "Groq"), ("xtts", "TTS")):
            row = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=26)
            row.pack(fill="x", padx=24, pady=2)
            self._label(row, name, 12, TEXT_2).pack(side="left")
            dot = ctk.CTkLabel(row, text="●", text_color="#334052", width=18, font=self._font(12, "bold"))
            dot.pack(side="right")
            self.dots[key] = dot
        self._label(self.sidebar, "OFFLINE-FIRST  •  WINDOWS", 9, MUTED, "bold").pack(side="bottom", anchor="w", padx=24, pady=22)

        self.content = ctk.CTkFrame(self, fg_color=BG)
        self.content.grid(row=0, column=1, sticky="nsew", padx=(4, 20), pady=18)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self._build_system_page()
        self._build_notes_page()
        self._build_reminders_page()
        self._build_settings_page()
        self.show_page("system")

    def _nav_button(self, icon, text, command):
        frame = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=42, corner_radius=10)
        frame.pack(fill="x", padx=14, pady=2)
        frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(frame, text=icon, width=28, text_color=MUTED, font=self._font(16)).grid(row=0, column=0, padx=(8, 3), pady=7)
        button = ctk.CTkButton(frame, text=text, anchor="w", fg_color="transparent", hover_color=PANEL_3, text_color=TEXT_2, font=self._font(12), height=38, corner_radius=9, command=command)
        button.grid(row=0, column=1, sticky="ew", padx=(0, 5))
        return frame, button

    def _page(self, key):
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        self._pages[key] = frame
        return frame

    def _build_system_page(self):
        p = self._page("system")
        header = ctk.CTkFrame(p, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.grid_columnconfigure(0, weight=1)
        self._label(header, "Система JARVIS", 28, TEXT, "bold").grid(row=0, column=0, sticky="w")
        self._label(header, "Локальный голосовой интерфейс и управление системой", 12, MUTED).grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.net_badge = ctk.CTkLabel(header, text="  ●  проверка сети  ", fg_color=PANEL, text_color=MUTED, corner_radius=12, font=self._font(11, "bold"))
        self.net_badge.grid(row=0, column=1, rowspan=2, sticky="e")

        body = ctk.CTkFrame(p, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)

        hero = self._card(body)
        hero.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        hero.grid_columnconfigure(1, weight=1)
        self.core_canvas = tk.Canvas(hero, width=142, height=142, bg=PANEL, highlightthickness=0)
        self.core_canvas.grid(row=0, column=0, rowspan=2, padx=(12, 22), pady=12)
        self._label(hero, "CENTRAL INTELLIGENCE", 10, MUTED, "bold").grid(row=0, column=1, sticky="sw", pady=(20, 0))
        self.status_text = self._label(hero, "Загрузка компонентов...", 21, TEXT, "bold")
        self.status_text.grid(row=1, column=1, sticky="nw", pady=(4, 20))
        self.hero_status = ctk.CTkLabel(hero, text="●  ИНИЦИАЛИЗАЦИЯ", text_color=WARN, fg_color="#2a2417", corner_radius=10, font=self._font(10, "bold"))
        self.hero_status.grid(row=0, column=2, rowspan=2, padx=24, pady=20, sticky="e")

        stats = ctk.CTkFrame(body, fg_color="transparent")
        stats.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        for i in range(3):
            stats.grid_columnconfigure(i, weight=1)
        self._stat_card(stats, 0, "STT", "GigaAM v3", "Речь → текст")
        self._stat_card(stats, 1, "WAKE", "Джарвис", "Голосовая активация")
        self._stat_card(stats, 2, "TTS", ENGINES.get(str(self.settings.get("tts_engine", "coqui")), "Coqui XTTS-v2"), "Выбранный движок")

        console = self._card(body)
        console.grid(row=2, column=0, sticky="nsew", pady=(0, 14))
        console.grid_rowconfigure(1, weight=1)
        console.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(console, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        self._label(top, "КОНСОЛЬ", 10, ACCENT, "bold").pack(side="left")
        self._label(top, "LOCAL SESSION", 9, MUTED, "bold").pack(side="right")
        self.log = ctk.CTkTextbox(console, fg_color="#0d141d", text_color=TEXT_2, border_width=0, corner_radius=10, font=self._font(12))
        self.log.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.log.configure(state="disabled")
        command = ctk.CTkFrame(body, fg_color="transparent")
        command.grid(row=3, column=0, sticky="ew")
        command.grid_columnconfigure(0, weight=1)
        self.entry = self._field(command, height=48, placeholder_text="Введите команду или вопрос...")
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.entry.bind("<Return>", lambda _event: self.send())
        ctk.CTkButton(command, text="➜", width=52, height=48, corner_radius=11, fg_color=ACCENT, hover_color="#69b7ff", text_color="#07111b", font=self._font(18, "bold"), command=self.send).grid(row=0, column=1, padx=(0, 8))
        self.mic = ctk.CTkButton(command, text="●", width=52, height=48, corner_radius=11, fg_color=PANEL_2, hover_color=PANEL_3, text_color=ACCENT, font=self._font(16, "bold"), command=self.mic_input, state="disabled")
        self.mic.grid(row=0, column=2)

    def _stat_card(self, parent, column, title, value, subtitle):
        card = self._card(parent)
        card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 6, 6 if column < 2 else 0))
        self._label(card, title, 9, ACCENT, "bold").pack(anchor="w", padx=14, pady=(12, 2))
        self._label(card, value, 15, TEXT, "bold").pack(anchor="w", padx=14)
        self._label(card, subtitle, 10, MUTED).pack(anchor="w", padx=14, pady=(1, 11))

    def _build_notes_page(self):
        p = self._page("notes")
        header = ctk.CTkFrame(p, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        self._label(header, "Заметки", 28, TEXT, "bold").pack(anchor="w")
        self._label(header, "Локальные заметки сохраняются на компьютере и не отправляются в Groq.", 12, MUTED).pack(anchor="w", pady=(3, 0))
        card = self._card(p)
        card.grid(row=1, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew", padx=16, pady=16)
        row.grid_columnconfigure(0, weight=1)
        self.note_entry = self._field(row, placeholder_text="Новая заметка...")
        self.note_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(row, text="Добавить", width=110, height=42, fg_color=ACCENT, text_color="#07111b", command=self.add_note_gui).grid(row=0, column=1)
        self.notes_box = ctk.CTkTextbox(card, fg_color="#0d141d", text_color=TEXT_2, corner_radius=10, font=self._font(12))
        self.notes_box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self._refresh_notes()

    def _build_reminders_page(self):
        p = self._page("reminders")
        header = ctk.CTkFrame(p, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        self._label(header, "Напоминания", 28, TEXT, "bold").pack(anchor="w")
        self._label(header, "JARVIS проверяет время в фоне. Напоминания сохраняются локально.", 12, MUTED).pack(anchor="w", pady=(3, 0))
        card = self._card(p)
        card.grid(row=1, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        row.grid_columnconfigure(0, weight=1)
        self.reminder_entry = self._field(row, placeholder_text="О чём напомнить...")
        self.reminder_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.reminder_when = self._field(row, width=180, placeholder_text="Например: 18:30")
        self.reminder_when.grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(row, text="Добавить", width=110, height=42, fg_color=ACCENT, text_color="#07111b", command=self.add_reminder_gui).grid(row=0, column=2)
        self._label(card, "Можно указать: 18:30, завтра в 10:00 или через 20 минут.", 10, MUTED).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))
        self.reminders_box = ctk.CTkTextbox(card, fg_color="#0d141d", text_color=TEXT_2, corner_radius=10, font=self._font(12))
        self.reminders_box.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self._refresh_reminders()

    def _build_settings_page(self):
        p = self._page("settings")
        header = ctk.CTkFrame(p, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self._label(header, "Настройки", 28, TEXT, "bold").pack(anchor="w")
        self._label(header, "Параметры JARVIS и голосового движка", 12, MUTED).pack(anchor="w", pady=(3, 0))
        scroll = ctk.CTkScrollableFrame(p, fg_color="transparent", scrollbar_button_color=BORDER, scrollbar_button_hover_color=ACCENT_SOFT)
        scroll.grid(row=1, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        self._label(scroll, "ПРОИЗВОДИТЕЛЬНОСТЬ", 11, ACCENT, "bold").grid(row=0, column=0, sticky="w", padx=4, pady=(2, 8))
        perf = self._card(scroll)
        perf.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        self._label(perf, "Режим работы", 13, TEXT, "bold").pack(anchor="w", padx=16, pady=(14, 1))
        self._label(perf, "Меняет количество CPU-потоков. Модели не выгружаются автоматически.", 10, MUTED).pack(anchor="w", padx=16, pady=(0, 10))
        current = str(self.settings.get("performance_mode", "balanced"))
        self.mode = tk.StringVar(value=MODES.get(current, MODES["balanced"])[0])
        self._option(perf, self.mode, [v[0] for v in MODES.values()], width=250, command=lambda _v: None).pack(anchor="w", padx=16, pady=(0, 15))

        self._label(scroll, "ОНЛАЙН-ОТВЕТЫ", 11, ACCENT, "bold").grid(row=2, column=0, sticky="w", padx=4, pady=(0, 8))
        online = self._card(scroll)
        online.grid(row=3, column=0, sticky="ew", pady=(0, 14))
        online.grid_columnconfigure(0, weight=1)
        online.grid_columnconfigure(1, weight=1)
        self._label(online, "Groq API-ключ", 10, MUTED).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 4))
        self._label(online, "Модель Groq", 10, MUTED).grid(row=0, column=1, sticky="w", padx=8, pady=(14, 4))
        self.groq = self._field(online, show="•", placeholder_text="Введите новый ключ для замены")
        self.groq.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))
        self._load_masked_key(self.groq, get_groq_api_key(self.settings))
        self.gmodel = self._field(online)
        self.gmodel.insert(0, self.settings.get("groq_model", "openai/gpt-oss-120b"))
        self.gmodel.grid(row=1, column=1, sticky="ew", padx=(8, 16), pady=(0, 14))

        self._label(scroll, "ГОЛОС JARVIS", 11, ACCENT, "bold").grid(row=4, column=0, sticky="w", padx=4, pady=(0, 8))
        voice = self._card(scroll)
        voice.grid(row=5, column=0, sticky="ew", pady=(0, 14))
        voice.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(voice, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=14)
        top.grid_columnconfigure(0, weight=1)
        self._label(top, "Движок озвучки", 14, TEXT, "bold").grid(row=0, column=0, sticky="w")
        engine_key = str(self.settings.get("tts_engine", "coqui"))
        self.engine = tk.StringVar(value=ENGINES.get(engine_key, ENGINES["coqui"]))
        self.engine_option = self._option(top, self.engine, list(ENGINES.values()), width=240, command=self._engine_changed)
        self.engine_option.grid(row=0, column=1, sticky="e")
        self.tts_stack = ctk.CTkFrame(voice, fg_color=PANEL_2, corner_radius=12)
        self.tts_stack.pack(fill="x", padx=12, pady=(0, 12))
        self.tts_stack.grid_columnconfigure(0, weight=1)
        self._make_coqui_panel()
        self._make_eleven_panel()
        self._make_silero_panel()
        self._show_engine(engine_key)

        self._label(scroll, "ГОЛОСОВАЯ АКТИВАЦИЯ", 11, ACCENT, "bold").grid(row=6, column=0, sticky="w", padx=4, pady=(0, 8))
        wake = self._card(scroll)
        wake.grid(row=7, column=0, sticky="ew", pady=(0, 18))
        self._label(wake, "Wake word", 14, TEXT, "bold").pack(anchor="w", padx=16, pady=(14, 1))
        self._label(wake, "Фраза активации: «Джарвис». Rustpotter слушает микрофон до обнаружения ключевого слова.", 10, TEXT_2, wraplength=760, justify="left").pack(anchor="w", padx=16, pady=(0, 10))
        self.wake = tk.BooleanVar(value=bool(self.settings.get("wake_word_enabled", True)))
        ctk.CTkCheckBox(wake, text="Включить голосовую активацию", variable=self.wake, text_color=TEXT, hover_color=ACCENT_SOFT, fg_color=ACCENT, border_color="#4b6178").pack(anchor="w", padx=16, pady=(0, 14))
        ctk.CTkButton(p, text="Сохранить настройки", width=150, height=38, corner_radius=10, fg_color=ACCENT, hover_color="#69b7ff", text_color="#07111b", font=self._font(11, "bold"), command=self.save).place(relx=0.99, rely=0.99, anchor="se")

    def _make_coqui_panel(self):
        self.coqui_panel = ctk.CTkFrame(self.tts_stack, fg_color="transparent")
        self.coqui_panel.grid_columnconfigure(0, weight=1)
        self._label(self.coqui_panel, "Reference WAV", 10, MUTED).grid(row=0, column=0, sticky="w", padx=14, pady=(13, 4))
        self.cwav = self._field(self.coqui_panel)
        self.cwav.insert(0, self.settings.get("xtts_speaker_wav", "resources/tts/jarvis_voice.wav"))
        self.cwav.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        row = ctk.CTkFrame(self.coqui_panel, fg_color="transparent")
        row.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 10))
        self._label(row, "Устройство", 10, MUTED).pack(side="left")
        self.cdev = tk.StringVar(value=self.settings.get("xtts_device", "cpu"))
        self._option(row, self.cdev, ["cpu", "cuda"], width=130).pack(side="right")
        self._label(self.coqui_panel, "Язык", 10, MUTED).grid(row=3, column=0, sticky="w", padx=14, pady=(0, 4))
        self.clang = self._field(self.coqui_panel)
        self.clang.insert(0, self.settings.get("xtts_language", "ru"))
        self.clang.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 10))
        self.csplit = tk.BooleanVar(value=bool(self.settings.get("xtts_split_sentences", True)))
        ctk.CTkCheckBox(self.coqui_panel, text="Разбивать длинные ответы на предложения", variable=self.csplit, text_color=TEXT_2, hover_color=ACCENT_SOFT, fg_color=ACCENT).grid(row=5, column=0, sticky="w", padx=14, pady=(0, 14))

    def _make_eleven_panel(self):
        self.eleven_panel = ctk.CTkFrame(self.tts_stack, fg_color="transparent")
        self.eleven_panel.grid_columnconfigure(0, weight=1)
        self.eleven_panel.grid_columnconfigure(1, weight=1)
        self._label(self.eleven_panel, "API-ключ ElevenLabs", 10, MUTED).grid(row=0, column=0, sticky="w", padx=14, pady=(13, 4))
        self._label(self.eleven_panel, "Voice ID", 10, MUTED).grid(row=0, column=1, sticky="w", padx=7, pady=(13, 4))
        self.ekey = self._field(self.eleven_panel, show="•", placeholder_text="Введите новый ключ")
        self.ekey.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        self._load_masked_key(self.ekey, get_elevenlabs_api_key(self.settings))
        self.evoice = self._field(self.eleven_panel, placeholder_text="Voice ID")
        self.evoice.insert(0, self.settings.get("elevenlabs_voice_id", ""))
        self.evoice.grid(row=1, column=1, sticky="ew", padx=7, pady=(0, 10))
        self._label(self.eleven_panel, "Модель", 10, MUTED).grid(row=2, column=0, sticky="w", padx=14, pady=(0, 4))
        self.emodel = tk.StringVar(value=self.settings.get("elevenlabs_model", "eleven_multilingual_v2"))
        self._option(self.eleven_panel, self.emodel, ["eleven_multilingual_v2", "eleven_flash_v2_5"], width=260).grid(row=3, column=0, sticky="w", padx=14, pady=(0, 14))

    def _make_silero_panel(self):
        self.silero_panel = ctk.CTkFrame(self.tts_stack, fg_color="transparent")
        self.silero_panel.grid_columnconfigure(0, weight=1)
        self.silero_panel.grid_columnconfigure(1, weight=1)
        self._label(self.silero_panel, "Голос", 10, MUTED).grid(row=0, column=0, sticky="w", padx=14, pady=(13, 4))
        self._label(self.silero_panel, "Устройство", 10, MUTED).grid(row=0, column=1, sticky="w", padx=7, pady=(13, 4))
        speaker_key = str(self.settings.get("silero_speaker", "eugene"))
        self.speaker = tk.StringVar(value=SILERO_SPEAKERS.get(speaker_key, SILERO_SPEAKERS["eugene"]))
        self._option(self.silero_panel, self.speaker, list(SILERO_SPEAKERS.values()), width=270).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 10))
        self.sdev = tk.StringVar(value=self.settings.get("silero_device", "cpu"))
        self._option(self.silero_panel, self.sdev, ["cpu", "cuda"], width=130).grid(row=1, column=1, sticky="w", padx=7, pady=(0, 10))
        self.srate = tk.StringVar(value=str(self.settings.get("silero_sample_rate", 48000)))
        self._option(self.silero_panel, self.srate, ["24000", "48000"], width=150).grid(row=2, column=0, sticky="w", padx=14, pady=(0, 14))

    def _load_masked_key(self, entry, value):
        if value:
            entry.insert(0, "•" * 16)

    def _engine_changed(self, displayed):
        reverse = {label: key for key, label in ENGINES.items()}
        self._show_engine(reverse.get(displayed, "coqui"))

    def _show_engine(self, key):
        for panel in (self.coqui_panel, self.eleven_panel, self.silero_panel):
            panel.grid_remove()
        panel = {"coqui": self.coqui_panel, "elevenlabs": self.eleven_panel, "silero": self.silero_panel}.get(key, self.coqui_panel)
        panel.grid(row=0, column=0, sticky="ew")

    def _current_mode_key(self):
        displayed = self.mode.get()
        return next((key for key, value in MODES.items() if value[0] == displayed), "balanced")

    def _current_speaker_key(self):
        displayed = self.speaker.get()
        return next((key for key, label in SILERO_SPEAKERS.items() if label == displayed), "eugene")

    def save(self):
        groq_value = self.groq.get().strip()
        if groq_value and groq_value != "•" * 16:
            self.settings["groq_api_key"] = groq_value
        eleven_value = self.ekey.get().strip()
        if eleven_value and eleven_value != "•" * 16:
            self.settings["elevenlabs_api_key"] = eleven_value
        self.settings.update({
            "performance_mode": self._current_mode_key(),
            "groq_model": self.gmodel.get().strip() or "openai/gpt-oss-120b",
            "tts_engine": next((key for key, label in ENGINES.items() if label == self.engine.get()), "coqui"),
            "xtts_speaker_wav": self.cwav.get().strip(),
            "xtts_device": self.cdev.get(),
            "xtts_language": self.clang.get().strip() or "ru",
            "xtts_split_sentences": bool(self.csplit.get()),
            "elevenlabs_voice_id": self.evoice.get().strip(),
            "elevenlabs_model": self.emodel.get(),
            "silero_speaker": self._current_speaker_key(),
            "silero_device": self.sdev.get(),
            "silero_sample_rate": int(self.srate.get()),
            "wake_word_enabled": bool(self.wake.get()),
        })
        save_settings(self.settings)
        jarvis_core.set_groq_model(self.settings["groq_model"])
        jarvis_core.reset_groq_client()
        self._show_toast("✓  Настройки сохранены")
        self._update_status_indicators()

    def _show_toast(self, text):
        if hasattr(self, "toast") and self.toast.winfo_exists():
            self.toast.destroy()
        self.toast = ctk.CTkLabel(self, text=text, fg_color="#173328", text_color=GOOD, corner_radius=12, font=self._font(11, "bold"))
        self.toast.place(relx=0.98, rely=0.92, anchor="e")
        self.after(2200, lambda: self.toast.destroy() if self.toast.winfo_exists() else None)

    # ---------- Notes / reminders ----------
    def _refresh_notes(self):
        notes = load_notes()
        lines = [f"{i}. {note.get('text', '')}" for i, note in enumerate(notes, 1)]
        self.notes_box.configure(state="normal")
        self.notes_box.delete("1.0", "end")
        self.notes_box.insert("1.0", "\n".join(lines) if lines else "Заметок пока нет.")
        self.notes_box.configure(state="disabled")

    def add_note_gui(self):
        text = self.note_entry.get().strip()
        if not text:
            return
        try:
            add_note(text)
            self.note_entry.delete(0, "end")
            self._refresh_notes()
            self.log_add("JARVIS", f"Заметка сохранена: {text}")
        except Exception as exc:
            self.log_add("ОШИБКА", str(exc))

    def _refresh_reminders(self):
        reminders = load_reminders()
        lines = []
        for i, reminder in enumerate(reminders, 1):
            try:
                import datetime as dt
                due = dt.datetime.fromisoformat(reminder["due_at"]).strftime("%d.%m.%Y в %H:%M")
            except Exception:
                due = reminder.get("when", "")
            lines.append(f"{i}. {due} — {reminder.get('text', '')}")
        self.reminders_box.configure(state="normal")
        self.reminders_box.delete("1.0", "end")
        self.reminders_box.insert("1.0", "\n".join(lines) if lines else "Активных напоминаний нет.")
        self.reminders_box.configure(state="disabled")

    def add_reminder_gui(self):
        text = self.reminder_entry.get().strip()
        when = self.reminder_when.get().strip()
        if not text or not when:
            return
        try:
            reminder = add_reminder(text, when)
            self.reminder_entry.delete(0, "end")
            self.reminder_when.delete(0, "end")
            self._refresh_reminders()
            self.log_add("JARVIS", f"Напоминание поставлено: {reminder['text']}")
        except Exception as exc:
            self.log_add("ОШИБКА", str(exc))

    def _on_reminder(self, reminder):
        text = reminder.get("text", "")
        self.after(0, lambda: self._refresh_reminders())
        self.after(0, lambda: self._show_reminder_toast(text))
        self.log_add("НАПОМИНАНИЕ", text)
        threading.Thread(target=self._speak_reminder, args=(text,), daemon=True).start()

    def _show_reminder_toast(self, text):
        toast = ctk.CTkLabel(self, text=f"🔔  Напоминание: {text}", fg_color="#2a2417", text_color=WARN, corner_radius=12, font=self._font(12, "bold"), wraplength=420)
        toast.place(relx=0.98, rely=0.08, anchor="ne")
        self.after(7000, lambda: toast.destroy() if toast.winfo_exists() else None)

    def _speak_reminder(self, text):
        try:
            jarvis_tts.speak(f"Напоминание. {text}")
        except Exception as exc:
            print(f"[Reminders] Ошибка озвучки: {exc}")

    # ---------- Runtime ----------
    def show_page(self, key):
        for page in self._pages.values():
            page.grid_remove()
        self._pages[key].grid()
        for name, nav in (("system", self.nav_system), ("notes", self.nav_notes), ("reminders", self.nav_reminders), ("settings", self.nav_settings)):
            frame, button = nav
            button.configure(fg_color=PANEL_3 if name == key else "transparent", text_color=TEXT if name == key else TEXT_2)

    def _update_network(self):
        try:
            online = bool(is_online())
        except Exception:
            online = False
        self.net_badge.configure(text="  ●  ONLINE  " if online else "  ●  OFFLINE  ", text_color=GOOD if online else MUTED, fg_color="#12261c" if online else PANEL)
        self.after(8000, self._update_network)

    def _update_status_indicators(self):
        self.dot("groq", bool(get_groq_api_key(self.settings)))
        self.dot("xtts", jarvis_tts.is_configured())

    def status_set(self, text):
        self.after(0, lambda: self.status_text.configure(text=text))

    def dot(self, key, value):
        if key in self.dots:
            self.after(0, lambda: self.dots[key].configure(text_color=GOOD if value else BAD))

    def load_models(self):
        try:
            self.status_set("Загрузка GigaAM и VAD...")
            jarvis_voice.warmup_voice_models()
            self.dot("gigaAM", True)
            self.dot("local", True)
            self.dot("groq", bool(get_groq_api_key(self.settings)))
            self.dot("xtts", jarvis_tts.is_configured())
            self.after(0, lambda: self.mic.configure(state="normal"))
            self.models_ready = True
            self.status_set("Система готова к работе")
            self.after(0, lambda: self.hero_status.configure(text="●  READY", text_color=GOOD, fg_color="#12261c"))
            try:
                jarvis_voice.play_sound(jarvis_voice.SOUND_RUN)
            except Exception:
                pass
            if self.settings.get("wake_word_enabled"):
                self.start_wake()
        except Exception as exc:
            print(f"[JARVIS] Ошибка запуска: {exc}")
            self.status_set("Ошибка загрузки компонентов")
            self.after(0, lambda: self.hero_status.configure(text="●  ERROR", text_color=BAD, fg_color="#2b171b"))
            self.dot("gigaAM", False)

    def start_wake(self):
        if self.wake_detector is not None or not self.models_ready:
            return
        try:
            from jarvis_wakeword import RustpotterWakeWordDetector
            cli = self.path(self.settings.get("rustpotter_cli_path", "resources/rustpotter/rustpotter-cli_win_x86_64.exe"))
            model = self.path(self.settings.get("rustpotter_model_path", "resources/rustpotter/jarvis-ru.rpw"))
            self.wake_detector = RustpotterWakeWordDetector(on_wake=self.wake_detect, cli_path=cli, model_path=model, threshold=float(self.settings.get("wake_word_threshold", 0.5)), device_index=int(self.settings.get("rustpotter_device_index", 0)))
            self.wake_detector.start()
            self.dot("wake", True)
        except Exception as exc:
            print(f"[WakeWord] {exc}")
            self.dot("wake", False)

    def _stop_wake(self):
        detector = self.wake_detector
        self.wake_detector = None
        if detector is not None:
            try:
                detector.stop()
            except Exception as exc:
                print(f"[WakeWord] stop: {exc}")
        self.dot("wake", False)

    def path(self, value):
        return value if os.path.isabs(value) else os.path.join(str(PROJECT_DIR), value)

    def wake_detect(self):
        if self.models_ready and not self._wake_running:
            self._wake_running = True
            threading.Thread(target=self.voice_reply, daemon=True).start()

    def voice_reply(self):
        try:
            self.after(0, lambda: self.mic.configure(state="disabled"))
            self._stop_wake()
            try:
                jarvis_voice.play_ack_sound()
            except Exception:
                pass
            self.status_set("Слушаю...")
            result = jarvis_voice.listen()
            self.status_set("Распознаю речь...")
            text = result.get("text", "")
            grammar = result.get("grammar_text")
            if text or grammar:
                self.process(text, grammar)
        except Exception as exc:
            self.log_add("ОШИБКА", str(exc))
        finally:
            self._wake_running = False
            self.after(0, lambda: self.mic.configure(state="normal" if self.models_ready else "disabled"))
            if self.models_ready and self.settings.get("wake_word_enabled"):
                self.start_wake()

    def send(self):
        text = self.entry.get().strip()
        self.entry.delete(0, "end")
        if text and self.models_ready:
            threading.Thread(target=self.process, args=(text,), daemon=True).start()

    def mic_input(self):
        if self.models_ready:
            threading.Thread(target=self.voice_reply, daemon=True).start()

    def process(self, text, grammar=None):
        try:
            self.status_set("Обрабатываю запрос...")
            result = jarvis_core.process_message(text, grammar_text=grammar, on_speak_ready=lambda value: jarvis_tts.speak(value))
            self.log_add("ВЫ", text)
            self.log_add("JARVIS", result.get("text", ""))
            if result.get("type") == "sound":
                jarvis_voice.play_sound(result["path"])
            elif result.get("type") == "local":
                jarvis_voice.play_random_ok()
            elif result.get("type") != "streamed":
                jarvis_tts.speak(result.get("text", ""))
        except Exception as exc:
            self.status_set("Ошибка")
            self.log_add("ОШИБКА", str(exc))
        finally:
            self.status_set("Система готова к работе")
            self.after(0, lambda: self.mic.configure(state="normal" if self.models_ready else "disabled"))
            self.after(0, self._refresh_reminders)

    def log_add(self, author, text):
        def update():
            if not hasattr(self, "log") or not self.log.winfo_exists():
                return
            self.log.configure(state="normal")
            self.log.insert("end", f"{author}\n{text}\n\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.after(0, update)

    def animate(self):
        self._anim_step = (self._anim_step + 1) % 120
        if hasattr(self, "core_canvas") and self.core_canvas.winfo_exists():
            c = self.core_canvas
            c.delete("all")
            cx = cy = 71
            pulse = 1.0 + 0.04 * ((self._anim_step % 30) / 30.0)
            rings = (58, 49, 38)
            for i, radius in enumerate(rings):
                r = radius * pulse
                c.create_oval(cx-r, cy-r, cx+r, cy+r, outline="#203b55" if i else "#2b5d85", width=2)
            for angle in range(0, 360, 45):
                import math
                rad = math.radians(angle + self._anim_step * 1.5)
                x1 = cx + 53 * math.cos(rad)
                y1 = cy + 53 * math.sin(rad)
                x2 = cx + 58 * math.cos(rad)
                y2 = cy + 58 * math.sin(rad)
                c.create_line(x1, y1, x2, y2, fill="#4aa8ff", width=2)
            c.create_oval(28, 28, 114, 114, fill="#162f49", outline="")
            c.create_text(cx, cy, text="J", fill=ACCENT, font=("Segoe UI", 38, "bold"))
        self.after(90, self.animate)

    def on_close(self):
        try:
            self.reminder_stop.set()
        except Exception:
            pass
        try:
            self._stop_wake()
            jarvis_voice.play_sound(jarvis_voice.SOUND_OFF)
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    JarvisApp().mainloop()
