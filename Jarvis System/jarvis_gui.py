from __future__ import annotations

import os
import threading
import tkinter as tk

import customtkinter as ctk

import jarvis_core
import jarvis_tts
import jarvis_voice
from jarvis_network import is_online
from jarvis_paths import PROJECT_DIR
from jarvis_settings import get_groq_api_key, get_elevenlabs_api_key, load_settings, save_settings

BG = "#080c12"
SIDEBAR = "#0d131b"
PANEL = "#111923"
PANEL_2 = "#151f2b"
PANEL_3 = "#192535"
FIELD = "#121b26"
BORDER = "#243244"
BORDER_SOFT = "#1b2735"
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
        self.dirty = False
        self._anim_step = 0
        self._wake_running = False

        self._build_ui()
        self._update_network()
        self.after(200, self._first_run)
        # GigaAM + VAD are kept ready. TTS is loaded lazily on first use.
        threading.Thread(target=self.load_models, daemon=True).start()
        self.animate()

    def _font(self, size=12, weight="normal"):
        return ctk.CTkFont(size=size, weight=weight)

    def _card(self, parent, **kwargs):
        return ctk.CTkFrame(parent, fg_color=kwargs.pop("fg_color", PANEL), corner_radius=16, border_width=1, border_color=kwargs.pop("border_color", BORDER_SOFT), **kwargs)

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
        return ctk.CTkOptionMenu(parent, variable=variable, values=values, width=width, height=40, corner_radius=10, fg_color=ACCENT_SOFT, button_color=ACCENT, button_hover_color="#68b7ff", dropdown_fg_color=PANEL_2, dropdown_hover_color=ACCENT_SOFT, text_color=TEXT, command=command)

    def _section_title(self, parent, text):
        return self._label(parent, text, size=11, color=ACCENT, weight="bold")

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.sidebar = ctk.CTkFrame(self, width=238, corner_radius=0, fg_color=SIDEBAR)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self._label(self.sidebar, "JARVIS", 29, TEXT, "bold").pack(anchor="w", padx=24, pady=(30, 0))
        self._label(self.sidebar, "LOCAL INTELLIGENCE", 10, ACCENT, "bold").pack(anchor="w", padx=25, pady=(1, 28))
        self.nav_system = self._nav_button("⌂", "Система", self.show_main)
        self.nav_settings = self._nav_button("⚙", "Настройки", self.show_settings)
        ctk.CTkFrame(self.sidebar, height=1, fg_color=BORDER_SOFT).pack(fill="x", padx=22, pady=24)
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
        self.main_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self.settings_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self.main_frame.grid(row=0, column=0, sticky="nsew")
        self.settings_frame.grid(row=0, column=0, sticky="nsew")
        self.settings_frame.grid_remove()
        self._build_main()
        self._build_settings()
        self.show_main()

    def _nav_button(self, icon, text, command):
        frame = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=44, corner_radius=10)
        frame.pack(fill="x", padx=14, pady=3)
        frame.grid_columnconfigure(1, weight=1)
        icon_label = ctk.CTkLabel(frame, text=icon, width=28, text_color=MUTED, font=self._font(16))
        icon_label.grid(row=0, column=0, padx=(8, 3), pady=8)
        button = ctk.CTkButton(frame, text=text, anchor="w", fg_color="transparent", hover_color=PANEL_3, text_color=TEXT_2, font=self._font(12), height=40, corner_radius=9, command=command)
        button.grid(row=0, column=1, sticky="ew", padx=(0, 5))
        return frame, button, icon_label

    def _build_main(self):
        p = self.main_frame
        p.grid_columnconfigure(0, weight=1)
        p.grid_rowconfigure(3, weight=1)
        header = ctk.CTkFrame(p, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.grid_columnconfigure(0, weight=1)
        self._label(header, "Система JARVIS", 28, TEXT, "bold").grid(row=0, column=0, sticky="w")
        self._label(header, "Локальный голосовой интерфейс и управление системой", 12, MUTED).grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.net_badge = ctk.CTkLabel(header, text="  ●  проверка сети  ", fg_color=PANEL, text_color=MUTED, corner_radius=12, font=self._font(11, "bold"))
        self.net_badge.grid(row=0, column=1, rowspan=2, sticky="e")

        hero = self._card(p, fg_color=PANEL)
        hero.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        hero.grid_columnconfigure(1, weight=1)
        hero.grid_columnconfigure(2, weight=0)
        orb = ctk.CTkFrame(
            hero, 
            width=116, 
            height=116, 
            fg_color="transparent"
        )
        orb.grid(row=0, column=0, rowspan=2, padx=(24, 26), pady=20)
        orb.grid_propagate(False)

        self.core = ctk.CTkLabel(
            orb, 
            text="J", 
            width=104, 
            height=104, 
            corner_radius=52, 
            fg_color="#162f49", 
            text_color=ACCENT, font=self._font(42, "bold")
        )
        self.core.place(relx=0.5, rely=0.5, anchor="center")
        self._label(hero, "CENTRAL INTELLIGENCE", 10, MUTED, "bold").grid(row=0, column=1, sticky="sw", pady=(20, 0))
        self.status_text = self._label(hero, "Загрузка компонентов...", 21, TEXT, "bold")
        self.status_text.grid(row=1, column=1, sticky="nw", pady=(4, 20))
        self.hero_status = ctk.CTkLabel(hero, text="●  ИНИЦИАЛИЗАЦИЯ", text_color=WARN, fg_color="#2a2417", corner_radius=10, font=self._font(10, "bold"))
        self.hero_status.grid(row=0, column=2, rowspan=2, padx=24, pady=20, sticky="e")
        self.scan_line = ctk.CTkFrame(hero, width=2, height=74, fg_color=ACCENT)
        self.scan_line.place(x=175, y=41)

        stats = ctk.CTkFrame(p, fg_color="transparent")
        stats.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        for i in range(3):
            stats.grid_columnconfigure(i, weight=1)
        self._stat_card(stats, 0, "STT", "GigaAM v3", "Речь → текст")
        self._stat_card(stats, 1, "WAKE", "Джарвис", "Голосовая активация")
        self._stat_card(stats, 2, "TTS", ENGINES.get(str(self.settings.get("tts_engine", "coqui")), "Coqui XTTS-v2"), "Выбранный движок")

        console = self._card(p, fg_color=PANEL)
        console.grid(row=3, column=0, sticky="nsew", pady=(0, 14))
        console.grid_rowconfigure(1, weight=1)
        console.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(console, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        self._label(top, "КОНСОЛЬ", 10, ACCENT, "bold").pack(side="left")
        self._label(top, "LOCAL SESSION", 9, MUTED, "bold").pack(side="right")
        self.log = ctk.CTkTextbox(console, fg_color="#0d141d", text_color=TEXT_2, border_width=0, corner_radius=10, font=self._font(12))
        self.log.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.log.configure(state="disabled")
        command = ctk.CTkFrame(p, fg_color="transparent")
        command.grid(row=4, column=0, sticky="ew")
        command.grid_columnconfigure(0, weight=1)
        self.entry = self._field(command, height=48, placeholder_text="Введите команду или вопрос...")
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.entry.bind("<Return>", lambda _event: self.send())
        self.send_button = ctk.CTkButton(command, text="➜", width=52, height=48, corner_radius=11, fg_color=ACCENT, hover_color="#69b7ff", text_color="#07111b", font=self._font(18, "bold"), command=self.send)
        self.send_button.grid(row=0, column=1, padx=(0, 8))
        self.mic = ctk.CTkButton(command, text="●", width=52, height=48, corner_radius=11, fg_color=PANEL_2, hover_color=PANEL_3, text_color=ACCENT, font=self._font(16, "bold"), command=self.mic_input, state="disabled")
        self.mic.grid(row=0, column=2)

    def _stat_card(self, parent, column, title, value, subtitle):
        card = self._card(parent, fg_color=PANEL)
        card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 6, 6 if column < 2 else 0))
        self._label(card, title, 9, ACCENT, "bold").pack(anchor="w", padx=14, pady=(12, 2))
        self._label(card, value, 15, TEXT, "bold").pack(anchor="w", padx=14)
        self._label(card, subtitle, 10, MUTED).pack(anchor="w", padx=14, pady=(1, 11))

    def _build_settings(self):
        p = self.settings_frame
        p.grid_columnconfigure(0, weight=1)
        p.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(p, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.grid_columnconfigure(0, weight=1)
        self._label(header, "Настройки", 28, TEXT, "bold").grid(row=0, column=0, sticky="w")
        self._label(header, "Параметры JARVIS и выбранного голосового движка", 12, MUTED).grid(row=1, column=0, sticky="w", pady=(3, 0))

        scroll = ctk.CTkScrollableFrame(p, fg_color="transparent", corner_radius=0, scrollbar_button_color=BORDER, scrollbar_button_hover_color=ACCENT_SOFT)
        scroll.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        scroll.grid_columnconfigure(0, weight=1)

        self._section_title(scroll, "ПРОИЗВОДИТЕЛЬНОСТЬ").grid(row=0, column=0, sticky="w", padx=4, pady=(2, 8))
        perf = self._card(scroll, fg_color=PANEL)
        perf.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        perf.grid_columnconfigure(0, weight=1)
        self._label(perf, "Режим работы", 13, TEXT, "bold").grid(row=0, column=0, sticky="w", padx=16, pady=(14, 1))
        self._label(perf, "Управляет количеством CPU-потоков. Модели не выгружаются автоматически.", 10, MUTED).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))
        current_mode = str(self.settings.get("performance_mode", "balanced"))
        self.mode = tk.StringVar(value=MODES.get(current_mode, MODES["balanced"])[0])
        mode_values = [name for name, _description in MODES.values()]
        self._option(perf, self.mode, mode_values, width=250, command=self._mark_dirty).grid(row=2, column=0, sticky="w", padx=16, pady=(0, 15))

        self._section_title(scroll, "ОНЛАЙН-ОТВЕТЫ").grid(row=2, column=0, sticky="w", padx=4, pady=(0, 8))
        online = self._card(scroll, fg_color=PANEL)
        online.grid(row=3, column=0, sticky="ew", pady=(0, 16))
        online.grid_columnconfigure(0, weight=1)
        online.grid_columnconfigure(1, weight=1)
        self._label(online, "Groq API-ключ", 11, MUTED).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 5))
        self._label(online, "Модель Groq", 11, MUTED).grid(row=0, column=1, sticky="w", padx=(8, 16), pady=(14, 5))
        self.groq = self._field(online, show="•", placeholder_text="Ключ сохранён — введите новый, чтобы заменить")
        self.groq.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))
        self._load_masked_key(self.groq, get_groq_api_key(self.settings))
        self.gmodel = self._field(online)
        self.gmodel.insert(0, self.settings.get("groq_model", "openai/gpt-oss-120b"))
        self.gmodel.grid(row=1, column=1, sticky="ew", padx=(8, 16), pady=(0, 14))

        self._section_title(scroll, "ГОЛОС JARVIS").grid(row=4, column=0, sticky="w", padx=4, pady=(0, 8))
        voice = self._card(scroll, fg_color=PANEL)
        voice.grid(row=5, column=0, sticky="ew", pady=(0, 16))
        voice.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(voice, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=14)
        top.grid_columnconfigure(0, weight=1)
        self._label(top, "Движок озвучки", 14, TEXT, "bold").grid(row=0, column=0, sticky="w")
        engine_key = str(self.settings.get("tts_engine", "coqui"))
        self.engine = tk.StringVar(value=ENGINES.get(engine_key, ENGINES["coqui"]))
        self.engine_option = self._option(top, self.engine, list(ENGINES.values()), width=240, command=self._engine_changed)
        self.engine_option.grid(row=0, column=1, sticky="e")
        self.engine_hint = self._label(voice, "", 10, MUTED, wraplength=760, justify="left")
        self.engine_hint.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))
        self.tts_stack = ctk.CTkFrame(voice, fg_color=PANEL_2, corner_radius=12)
        self.tts_stack.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        self.tts_stack.grid_columnconfigure(0, weight=1)
        self._make_coqui_panel()
        self._make_eleven_panel()
        self._make_silero_panel()
        self._show_engine(engine_key)

        self._section_title(scroll, "ГОЛОСОВАЯ АКТИВАЦИЯ").grid(row=6, column=0, sticky="w", padx=4, pady=(0, 8))
        wake = self._card(scroll, fg_color=PANEL)
        wake.grid(row=7, column=0, sticky="ew", pady=(0, 22))
        wake.grid_columnconfigure(0, weight=1)
        self._label(wake, "Wake word", 14, TEXT, "bold").grid(row=0, column=0, sticky="w", padx=16, pady=(14, 1))
        self._label(wake, "Фраза активации: «Джарвис». Rustpotter слушает микрофон до обнаружения ключевого слова.", 10, TEXT_2, wraplength=760, justify="left").grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))
        self.wake = tk.BooleanVar(value=bool(self.settings.get("wake_word_enabled", True)))
        ctk.CTkCheckBox(wake, text="Включить голосовую активацию", variable=self.wake, text_color=TEXT, hover_color=ACCENT_SOFT, fg_color=ACCENT, border_color="#4b6178", command=self._mark_dirty).grid(row=2, column=0, sticky="w", padx=16, pady=(0, 14))

        self.save_bar = ctk.CTkFrame(p, fg_color=PANEL, corner_radius=14, border_width=1, border_color=BORDER)
        self.save_bar.place(relx=0.99, rely=0.99, anchor="se")
        self.save_state = self._label(self.save_bar, "Все изменения сохранены", 10, MUTED)
        self.save_state.pack(side="left", padx=(14, 10), pady=9)
        self.save_button = ctk.CTkButton(self.save_bar, text="Сохранить", width=118, height=34, corner_radius=9, fg_color=ACCENT, hover_color="#69b7ff", text_color="#07111b", font=self._font(11, "bold"), command=self.save)
        self.save_button.pack(side="right", padx=(0, 7), pady=6)

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
        ctk.CTkCheckBox(self.coqui_panel, text="Разбивать длинные ответы на предложения", variable=self.csplit, text_color=TEXT_2, hover_color=ACCENT_SOFT, fg_color=ACCENT, command=self._mark_dirty).grid(row=5, column=0, sticky="w", padx=14, pady=(0, 14))

    def _make_eleven_panel(self):
        self.eleven_panel = ctk.CTkFrame(self.tts_stack, fg_color="transparent")
        self.eleven_panel.grid_columnconfigure(0, weight=1)
        self.eleven_panel.grid_columnconfigure(1, weight=1)
        self._label(self.eleven_panel, "API-ключ ElevenLabs", 10, MUTED).grid(row=0, column=0, sticky="w", padx=14, pady=(13, 4))
        self._label(self.eleven_panel, "Voice ID", 10, MUTED).grid(row=0, column=1, sticky="w", padx=(7, 14), pady=(13, 4))
        self.ekey = self._field(self.eleven_panel, show="•", placeholder_text="Ключ сохранён — введите новый")
        self.ekey.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        self._load_masked_key(self.ekey, get_elevenlabs_api_key(self.settings))
        self.evoice = self._field(self.eleven_panel, placeholder_text="Voice ID")
        self.evoice.insert(0, self.settings.get("elevenlabs_voice_id", ""))
        self.evoice.grid(row=1, column=1, sticky="ew", padx=(7, 14), pady=(0, 10))
        self._label(self.eleven_panel, "Модель", 10, MUTED).grid(row=2, column=0, sticky="w", padx=14, pady=(0, 4))
        self.emodel = tk.StringVar(value=self.settings.get("elevenlabs_model", "eleven_multilingual_v2"))
        self._option(self.eleven_panel, self.emodel, ["eleven_multilingual_v2", "eleven_flash_v2_5"], width=260).grid(row=3, column=0, sticky="w", padx=14, pady=(0, 14))

    def _make_silero_panel(self):
        self.silero_panel = ctk.CTkFrame(self.tts_stack, fg_color="transparent")
        self.silero_panel.grid_columnconfigure(0, weight=1)
        self.silero_panel.grid_columnconfigure(1, weight=1)
        self._label(self.silero_panel, "Голос", 10, MUTED).grid(row=0, column=0, sticky="w", padx=14, pady=(13, 4))
        self._label(self.silero_panel, "Устройство", 10, MUTED).grid(row=0, column=1, sticky="w", padx=(7, 14), pady=(13, 4))
        speaker_key = str(self.settings.get("silero_speaker", "eugene"))
        self.speaker = tk.StringVar(value=SILERO_SPEAKERS.get(speaker_key, SILERO_SPEAKERS["eugene"]))
        self._option(self.silero_panel, self.speaker, list(SILERO_SPEAKERS.values()), width=270).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 10))
        self.sdev = tk.StringVar(value=self.settings.get("silero_device", "cpu"))
        self._option(self.silero_panel, self.sdev, ["cpu", "cuda"], width=130).grid(row=1, column=1, sticky="w", padx=(7, 14), pady=(0, 10))
        self._label(self.silero_panel, "Частота дискретизации", 10, MUTED).grid(row=2, column=0, sticky="w", padx=14, pady=(0, 4))
        self.srate = tk.StringVar(value=str(self.settings.get("silero_sample_rate", 48000)))
        self._option(self.silero_panel, self.srate, ["24000", "48000"], width=150).grid(row=3, column=0, sticky="w", padx=14, pady=(0, 14))

    def _load_masked_key(self, entry, value):
        if value:
            entry.delete(0, "end")
            entry.insert(0, "•" * 16)

    def _mark_dirty(self, *_):
        self.dirty = True
        self.save_state.configure(text="Есть несохранённые изменения", text_color=WARN)

    def _engine_changed(self, displayed):
        reverse = {label: key for key, label in ENGINES.items()}
        self._show_engine(reverse.get(displayed, "coqui"), mark_dirty=True)

    def _show_engine(self, key, mark_dirty=False):
        for panel in (self.coqui_panel, self.eleven_panel, self.silero_panel):
            panel.grid_remove()
        hints = {
            "coqui": "Coqui XTTS-v2 — локальное клонирование голоса. Reference WAV используется как образец тембра.",
            "elevenlabs": "ElevenLabs — облачная озвучка через API. Требуется API-ключ и Voice ID.",
            "silero": "Silero TTS — локальная озвучка с готовыми русскими голосами.",
        }
        panel = {"coqui": self.coqui_panel, "elevenlabs": self.eleven_panel, "silero": self.silero_panel}.get(key, self.coqui_panel)
        panel.grid(row=0, column=0, sticky="ew")
        self.engine_hint.configure(text=hints.get(key, ""))
        if mark_dirty:
            self._mark_dirty()

    def _current_mode_key(self):
        displayed = self.mode.get()
        for key, (name, _description) in MODES.items():
            if displayed == name:
                return key
        return "balanced"

    def _current_speaker_key(self):
        displayed = self.speaker.get()
        for key, label in SILERO_SPEAKERS.items():
            if displayed == label:
                return key
        return "eugene"

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
        self.dirty = False
        self.save_state.configure(text="✓  Настройки сохранены", text_color=GOOD)
        self._show_toast("✓  Настройки сохранены")
        self._update_status_indicators()

    def _show_toast(self, text):
        if hasattr(self, "toast") and self.toast.winfo_exists():
            self.toast.destroy()
        self.toast = ctk.CTkLabel(self, text=text, fg_color="#173328", text_color=GOOD, corner_radius=12, font=self._font(11, "bold"))
        self.toast.place(relx=1.04, rely=0.92, anchor="e")
        self._toast_slide(0)

    def _toast_slide(self, step):
        if not self.toast.winfo_exists():
            return
        if step < 12:
            self.toast.place_configure(relx=1.04 - (0.04 * (step + 1) / 12))
            self.after(18, lambda: self._toast_slide(step + 1))
        else:
            self.after(1900, self._hide_toast)

    def _hide_toast(self):
        if not self.toast.winfo_exists():
            return
        self.toast.place_configure(relx=1.04)
        self.after(180, self.toast.destroy)

    # ---------- Runtime ----------
    def _update_network(self):
        try:
            online = bool(is_online())
        except Exception:
            online = False
        if online:
            self.net_badge.configure(text="  ●  ONLINE  ", text_color=GOOD, fg_color="#12261c")
        else:
            self.net_badge.configure(text="  ●  OFFLINE  ", text_color=MUTED, fg_color=PANEL)
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
                self.status_set("Обрабатываю запрос...")
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
            if result.get("type") == "streamed":
                self.status_set("Получаю ответ...")
            else:
                self.status_set("Воспроизвожу ответ...")

            self.log_add("JARVIS", result.get("text", ""))

            if result.get("type") == "sound":
                self.status_set("Воспроизвожу звук...")
                jarvis_voice.play_sound(result["path"])
            elif result.get("type") == "local":
                self.status_set("Воспроизвожу ответ...")
                jarvis_voice.play_random_ok()
            elif result.get("type") != "streamed":
                self.status_set("Воспроизвожу ответ...")
                jarvis_tts.speak(result.get("text", ""))
        except Exception as exc:
            self.status_set("Ошибка")
            self.log_add("ОШИБКА", str(exc))
        finally:
            self.status_set("Система готова к работе")
            self.after(0, lambda: self.mic.configure(state="normal" if self.models_ready else "disabled"))

    def log_add(self, author, text):
        def update():
            self.log.configure(state="normal")
            self.log.insert("end", f"{author}\n{text}\n\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.after(0, update)

    def show_main(self):
        self.settings_frame.grid_remove()
        self.main_frame.grid()
        self._set_nav(self.nav_system, True)
        self._set_nav(self.nav_settings, False)

    def show_settings(self):
        self.main_frame.grid_remove()
        self.settings_frame.grid()
        self._set_nav(self.nav_system, False)
        self._set_nav(self.nav_settings, True)

    def _set_nav(self, nav, active):
        _frame, button, icon = nav
        if active:
            button.configure(fg_color=PANEL_3, text_color=TEXT)
            icon.configure(text_color=ACCENT)
        else:
            button.configure(fg_color="transparent", text_color=TEXT_2)
            icon.configure(text_color=MUTED)

    def animate(self):
        self._anim_step = (self._anim_step + 1) % 60
        if self.models_ready:
            phase = self._anim_step % 20
            self.core.configure(fg_color="#1a3a5a" if phase < 10 else "#152f4a")
            try:
                self.scan_line.place_configure(x=175 + ((self._anim_step * 8) % 520))
            except Exception:
                pass
        else:
            self.core.configure(fg_color="#142131")
        self.after(90, self.animate)

    def _first_run(self):
        self.entry.focus_set()

    def on_close(self):
        try:
            self._stop_wake()
            jarvis_voice.play_sound(jarvis_voice.SOUND_OFF)
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    JarvisApp().mainloop()
