import os
import threading
import tkinter as tk

import customtkinter as ctk

import jarvis_core
import jarvis_tts
import jarvis_voice
from jarvis_network import is_online
from jarvis_paths import PROJECT_DIR
from jarvis_settings import get_groq_api_key, load_settings, save_settings

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BG = "#080b10"
PANEL = "#10151d"
PANEL_2 = "#151b24"
BORDER = "#252d38"
ACCENT = "#4aa8ff"
TEXT = "#edf2f7"
MUTED = "#7f8b99"
GOOD = "#55d187"
WARN = "#ffd166"
BAD = "#ff6b6b"


class JarvisApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("JARVIS")
        self.geometry("1050x720")
        self.minsize(900, 620)
        self.configure(fg_color=BG)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.settings = load_settings()
        self.models_ready = False
        self.wake_detector = None
        self.settings_dirty = False
        self._settings_tracking_ready = False
        self._groq_key_editing = False

        self._build_ui()
        self._setup_settings_change_tracking()
        self.after(250, self._show_first_run_groq_setup)
        threading.Thread(target=self._load_models_thread, daemon=True).start()

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(
            self, width=220, corner_radius=0, fg_color=PANEL,
            border_width=1, border_color=BORDER
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=22, pady=(28, 30))
        ctk.CTkLabel(
            brand, text="JARVIS", text_color=TEXT,
            font=ctk.CTkFont(size=28, weight="bold")
        ).pack(anchor="w")
        ctk.CTkLabel(
            brand, text="LOCAL AI SYSTEM", text_color=ACCENT,
            font=ctk.CTkFont(size=10, weight="bold")
        ).pack(anchor="w", pady=(2, 0))

        self.nav_main = self._nav_button("⌂  Система", self._show_main)
        self.nav_settings = self._nav_button("⚙  Настройки", self._show_settings)
        self.nav_main.pack(fill="x", padx=12, pady=4)
        self.nav_settings.pack(fill="x", padx=12, pady=4)
        self.nav_main.configure(fg_color="#1c2734")

        ctk.CTkFrame(self.sidebar, height=1, fg_color=BORDER).pack(
            fill="x", padx=18, pady=20
        )
        ctk.CTkLabel(
            self.sidebar, text="СОСТОЯНИЕ СИСТЕМЫ", text_color=MUTED,
            font=ctk.CTkFont(size=10, weight="bold")
        ).pack(anchor="w", padx=22, pady=(0, 10))

        self.component_labels = {}
        for key, title in (
            ("vosk", "Vosk STT"),
            ("wake", "Wake word"),
            ("local", "Local commands"),
            ("groq", "Groq"),
            ("xtts", "XTTS-v2"),
        ):
            row = ctk.CTkFrame(self.sidebar, fg_color="transparent")
            row.pack(fill="x", padx=22, pady=3)
            ctk.CTkLabel(row, text=title, text_color=MUTED, anchor="w").pack(
                side="left", fill="x", expand=True
            )
            dot = ctk.CTkLabel(row, text="●", text_color="#39414d", width=18)
            dot.pack(side="right")
            self.component_labels[key] = dot

        bottom = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=22, pady=20)
        ctk.CTkLabel(
            bottom, text="Offline-first • Windows", text_color=MUTED,
            font=ctk.CTkFont(size=10)
        ).pack(anchor="w")

        self.content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew", padx=18, pady=18)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.main_page = ctk.CTkFrame(self.content, fg_color="transparent")
        self.settings_page = ctk.CTkFrame(self.content, fg_color="transparent")
        self.main_page.grid(row=0, column=0, sticky="nsew")
        self.settings_page.grid(row=0, column=0, sticky="nsew")
        self.settings_page.grid_remove()
        self._build_main_page()
        self._build_settings_page()

    def _nav_button(self, text, command):
        return ctk.CTkButton(
            self.sidebar, text=text, command=command, anchor="w", height=42,
            corner_radius=9, fg_color="transparent", hover_color=PANEL_2,
            text_color=TEXT, font=ctk.CTkFont(size=13, weight="bold")
        )

    def _show_main(self):
        self.settings_page.grid_remove()
        self.main_page.grid()
        self.nav_main.configure(fg_color="#1c2734")
        self.nav_settings.configure(fg_color="transparent")

    def _show_settings(self):
        self.main_page.grid_remove()
        self.settings_page.grid()
        self.nav_main.configure(fg_color="transparent")
        self.nav_settings.configure(fg_color="#1c2734")

    def _build_main_page(self):
        page = self.main_page
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(page, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.grid_columnconfigure(0, weight=1)
        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_box, text="Система JARVIS", text_color=TEXT,
            font=ctk.CTkFont(size=25, weight="bold")
        ).pack(anchor="w")
        self.network_label = ctk.CTkLabel(
            title_box, text="Проверка сети...", text_color=MUTED,
            font=ctk.CTkFont(size=11)
        )
        self.network_label.pack(anchor="w", pady=(2, 0))
        self.status_pill = ctk.CTkLabel(
            header, text="  ЗАГРУЗКА  ", text_color=MUTED,
            fg_color=PANEL, corner_radius=16,
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.status_pill.grid(row=0, column=1, sticky="e")

        hero = ctk.CTkFrame(
            page, fg_color=PANEL, corner_radius=18,
            border_width=1, border_color=BORDER
        )
        hero.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        hero.grid_columnconfigure(1, weight=1)
        self.core_indicator = ctk.CTkLabel(
            hero, text="J", width=100, height=100, corner_radius=50,
            fg_color="#16283b", text_color=ACCENT,
            font=ctk.CTkFont(size=42, weight="bold")
        )
        self.core_indicator.grid(row=0, column=0, rowspan=2, padx=28, pady=24)
        ctk.CTkLabel(
            hero, text="CENTRAL INTELLIGENCE", text_color=MUTED,
            font=ctk.CTkFont(size=10, weight="bold")
        ).grid(row=0, column=1, sticky="sw", pady=(22, 0))
        self.status_label = ctk.CTkLabel(
            hero, text="Загрузка компонентов...", text_color=TEXT,
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.status_label.grid(row=1, column=1, sticky="nw", pady=(3, 24))
        self.wake_status_label = ctk.CTkLabel(
            hero, text="Wake word: инициализация...", text_color=MUTED,
            font=ctk.CTkFont(size=11)
        )
        self.wake_status_label.grid(row=0, column=2, padx=28, pady=(22, 0), sticky="e")

        self.log_box = ctk.CTkTextbox(
            page, fg_color=PANEL, border_width=1, border_color=BORDER,
            corner_radius=14, wrap="word", font=ctk.CTkFont(size=13)
        )
        self.log_box.grid(row=2, column=0, sticky="nsew", pady=(0, 14))
        self.log_box.configure(state="disabled")

        input_frame = ctk.CTkFrame(page, fg_color="transparent")
        input_frame.grid(row=3, column=0, sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)
        self.text_entry = ctk.CTkEntry(
            input_frame, height=46, corner_radius=12,
            fg_color=PANEL, border_color=BORDER,
            placeholder_text="Введите команду или вопрос..."
        )
        self.text_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.text_entry.bind("<Return>", lambda event: self.on_send_text())
        self.send_button = ctk.CTkButton(
            input_frame, text="➤", width=54, height=46, corner_radius=12,
            command=self.on_send_text
        )
        self.send_button.grid(row=0, column=1, padx=(0, 8))
        self.mic_button = ctk.CTkButton(
            input_frame, text="🎙", width=54, height=46, corner_radius=12,
            command=self.on_mic_button, state="disabled"
        )
        self.mic_button.grid(row=0, column=2)
        ctk.CTkLabel(
            page, text="Enter — отправить   •   🎙 — голосовой ввод   •   Wake word — «Джарвис»",
            text_color=MUTED, font=ctk.CTkFont(size=10)
        ).grid(row=4, column=0, sticky="w", pady=(7, 0))

    def _build_settings_page(self):
        page = self.settings_page
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(page, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        ctk.CTkLabel(
            header, text="Настройки", text_color=TEXT,
            font=ctk.CTkFont(size=25, weight="bold")
        ).pack(anchor="w")
        ctk.CTkLabel(
            header, text="Конфигурация голосовой системы и онлайн-ответов",
            text_color=MUTED
        ).pack(anchor="w", pady=(2, 0))

        scroll = ctk.CTkScrollableFrame(
            page, fg_color=PANEL, corner_radius=16,
            border_width=1, border_color=BORDER
        )
        scroll.grid(row=1, column=0, sticky="nsew")

        self.unsaved_banner = ctk.CTkFrame(scroll, fg_color="#302915", corner_radius=10)
        self.unsaved_banner.pack(fill="x", padx=4, pady=(4, 12))
        ctk.CTkLabel(
            self.unsaved_banner, text="Есть несохранённые изменения",
            text_color=WARN, font=ctk.CTkFont(weight="bold")
        ).pack(side="left", padx=12, pady=8)
        ctk.CTkButton(
            self.unsaved_banner, text="Сохранить", width=110, height=30,
            command=self.on_save_settings
        ).pack(side="right", padx=8, pady=6)
        self.unsaved_banner.pack_forget()

        self._section(scroll, "ОНЛАЙН-ОТВЕТЫ")
        self._label(scroll, "API-ключ Groq")
        key_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        key_frame.pack(fill="x", padx=4, pady=(0, 10))
        self.groq_key_entry = ctk.CTkEntry(
            key_frame, show="•", placeholder_text="Введите API-ключ"
        )
        self.groq_key_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.groq_key_entry.bind("<FocusIn>", self._on_groq_key_focus_in)
        self.groq_key_entry.bind("<FocusOut>", self._on_groq_key_focus_out)
        ctk.CTkButton(
            key_frame, text="Удалить", width=90, command=self._clear_groq_key
        ).pack(side="right")
        self._refresh_groq_key_field()

        self._label(scroll, "Модель Groq")
        self.model_entry = ctk.CTkEntry(scroll)
        self.model_entry.insert(0, self.settings["groq_model"])
        self.model_entry.pack(fill="x", padx=4, pady=(0, 18))

        self._section(scroll, "ГОЛОС JARVIS — XTTS-V2")
        ctk.CTkLabel(
            scroll,
            text="Модель скачивается автоматически при первом использовании и хранится в Models\\TTS.",
            text_color=MUTED, justify="left"
        ).pack(anchor="w", padx=4, pady=(0, 12))
        self._label(scroll, "Reference WAV")
        self.voice_wav_entry = ctk.CTkEntry(scroll)
        self.voice_wav_entry.insert(
            0, self.settings.get("xtts_speaker_wav", "resources/tts/jarvis_voice.wav")
        )
        self.voice_wav_entry.pack(fill="x", padx=4, pady=(0, 10))

        device_row = ctk.CTkFrame(scroll, fg_color="transparent")
        device_row.pack(fill="x", padx=4, pady=(0, 10))
        device_row.grid_columnconfigure(0, weight=1)
        device_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(device_row, text="Устройство XTTS", text_color=MUTED).grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        ctk.CTkLabel(device_row, text="Язык", text_color=MUTED).grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )
        self.device_var = tk.StringVar(value=self.settings.get("xtts_device", "cpu"))
        self.device_menu = ctk.CTkOptionMenu(
            device_row, variable=self.device_var, values=["cpu", "cuda"]
        )
        self.device_menu.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(4, 0))
        self.language_entry = ctk.CTkEntry(device_row)
        self.language_entry.insert(0, self.settings.get("xtts_language", "ru"))
        self.language_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(4, 0))

        self._label(scroll, "Пауза по краям WAV (мс)")
        self.padding_slider = ctk.CTkSlider(scroll, from_=0, to=200, number_of_steps=40)
        self.padding_slider.set(self.settings.get("xtts_playback_padding_ms", 80))
        self.padding_slider.pack(fill="x", padx=4, pady=(0, 8))
        self.split_var = tk.BooleanVar(value=self.settings.get("xtts_split_sentences", True))
        ctk.CTkCheckBox(
            scroll, text="Разбивать длинный текст на предложения", variable=self.split_var
        ).pack(anchor="w", padx=4, pady=(0, 8))

        self._section(scroll, "ГОЛОСОВОЙ ИНТЕРФЕЙС")
        self.wake_word_var = tk.BooleanVar(value=self.settings.get("wake_word_enabled", True))
        ctk.CTkCheckBox(
            scroll, text='Реагировать на «Джарвис» без кнопки', variable=self.wake_word_var
        ).pack(anchor="w", padx=4, pady=(0, 18))
        ctk.CTkButton(
            scroll, text="Сохранить настройки", height=42,
            command=self.on_save_settings
        ).pack(fill="x", padx=4, pady=(0, 8))
        self.settings_status_label = ctk.CTkLabel(scroll, text="", text_color=GOOD)
        self.settings_status_label.pack(pady=(0, 16))

    def _section(self, parent, text):
        ctk.CTkLabel(
            parent, text=text, text_color=ACCENT,
            font=ctk.CTkFont(size=11, weight="bold")
        ).pack(anchor="w", padx=4, pady=(8, 10))

    def _label(self, parent, text):
        ctk.CTkLabel(parent, text=text, text_color=MUTED, anchor="w").pack(
            fill="x", padx=4, pady=(0, 4)
        )

    def _setup_settings_change_tracking(self):
        for entry in (self.model_entry, self.voice_wav_entry, self.language_entry):
            entry.bind("<KeyRelease>", lambda event: self._mark_settings_dirty(), add="+")
        self.groq_key_entry.bind(
            "<KeyRelease>", lambda event: self._mark_settings_dirty(), add="+"
        )
        self.device_var.trace_add("write", lambda *_: self._mark_settings_dirty())
        self.padding_slider.configure(command=lambda value: self._mark_settings_dirty())
        self.split_var.trace_add("write", lambda *_: self._mark_settings_dirty())
        self.wake_word_var.trace_add("write", lambda *_: self._mark_settings_dirty())
        self._settings_tracking_ready = True

    def _mark_settings_dirty(self):
        if not self._settings_tracking_ready:
            return
        self.settings_dirty = True
        self.unsaved_banner.pack(fill="x", padx=4, pady=(4, 12))
        self.settings_status_label.configure(text="Изменения не сохранены.", text_color=WARN)

    def _mark_settings_clean(self):
        self.settings_dirty = False
        self.unsaved_banner.pack_forget()
        self.settings_status_label.configure(text="Настройки сохранены.", text_color=GOOD)

    def _refresh_groq_key_field(self):
        self._groq_key_editing = False
        self.groq_key_entry.delete(0, "end")
        local_key = (self.settings.get("groq_api_key") or "").strip()
        env_key = os.environ.get("GROQ_API_KEY", "").strip()
        if local_key:
            self.groq_key_entry.insert(0, "•" * max(8, len(local_key)))
            self.groq_key_entry.configure(placeholder_text="API-ключ сохранён")
        elif env_key:
            self.groq_key_entry.insert(0, "•" * 16)
            self.groq_key_entry.configure(placeholder_text="Ключ задан через Windows")
        else:
            self.groq_key_entry.configure(placeholder_text="Введите API-ключ")

    def _on_groq_key_focus_in(self, _event=None):
        if not self._groq_key_editing:
            self._groq_key_editing = True
            self.groq_key_entry.delete(0, "end")
            self.groq_key_entry.configure(placeholder_text="Введите новый API-ключ")

    def _on_groq_key_focus_out(self, _event=None):
        if self._groq_key_editing and not self.groq_key_entry.get().strip():
            self._refresh_groq_key_field()

    def _clear_groq_key(self):
        self._groq_key_editing = True
        self.groq_key_entry.delete(0, "end")
        self.groq_key_entry.configure(placeholder_text="Ключ будет удалён после сохранения")
        self.settings["groq_api_key"] = ""
        self._mark_settings_dirty()

    def _show_first_run_groq_setup(self):
        if get_groq_api_key(self.settings):
            return
        dialog = ctk.CTkToplevel(self)
        dialog.title("Настройка JARVIS")
        dialog.geometry("520x300")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        ctk.CTkLabel(
            dialog, text="Добро пожаловать в JARVIS",
            font=ctk.CTkFont(size=22, weight="bold")
        ).pack(pady=(24, 8))
        ctk.CTkLabel(
            dialog,
            text="Для онлайн-ответов нужен API-ключ Groq.\nЕго можно добавить сейчас или позже в настройках.",
            justify="center"
        ).pack(pady=(0, 18))
        entry = ctk.CTkEntry(dialog, show="•", width=440, placeholder_text="Вставьте API-ключ Groq")
        entry.pack(pady=(0, 16))
        entry.focus_set()
        buttons = ctk.CTkFrame(dialog, fg_color="transparent")
        buttons.pack(fill="x", padx=40)

        def save_first_key():
            key = entry.get().strip()
            if not key:
                return
            self.settings["groq_api_key"] = key
            save_settings(self.settings)
            jarvis_core.reset_groq_client()
            self._refresh_groq_key_field()
            self._mark_settings_clean()
            dialog.destroy()

        ctk.CTkButton(buttons, text="Сохранить", command=save_first_key).pack(
            side="left", expand=True, padx=5
        )
        ctk.CTkButton(
            buttons, text="Пропустить", command=dialog.destroy,
            fg_color="#343b45", hover_color="#424b57"
        ).pack(side="right", expand=True, padx=5)

    def _load_models_thread(self):
        try:
            self.set_status("Загружаю Vosk...")
            jarvis_voice.get_vosk_model()
            self._set_component("vosk", True)
            self.set_status("Проверяю сеть...")
            self._refresh_network_status()
            if is_online() and get_groq_api_key(self.settings):
                try:
                    self.set_status("Проверяю связь с Groq...")
                    jarvis_core.warmup()
                    self._set_component("groq", True)
                except Exception as e:
                    self._set_component("groq", False)
                    print(f"[Предупреждение] Groq недоступна: {e}")
            else:
                self._set_component("groq", False)
            self._set_component("local", True)
            self._set_component("xtts", jarvis_tts.is_configured())
            self.models_ready = True
            self.set_status("Готов к работе")
            self.after(0, lambda: self.mic_button.configure(state="normal"))
            jarvis_voice.play_sound(jarvis_voice.SOUND_RUN)
            if self.settings.get("wake_word_enabled"):
                self._start_wake_word()
            else:
                self._set_component("wake", False)
        except Exception as e:
            self.set_status(f"Ошибка загрузки: {e}")
            self._set_component("vosk", False)
            print(f"[JARVIS] Ошибка запуска: {e}")

    def _set_component(self, key, ok):
        dot = self.component_labels.get(key)
        if not dot:
            return
        color = GOOD if ok else BAD
        self.after(0, lambda d=dot, c=color: d.configure(text_color=c))

    def _start_wake_word(self):
        try:
            from jarvis_wakeword import RustpotterWakeWordDetector
            cli_path = self._project_path(self.settings.get("rustpotter_cli_path", ""))
            model_path = self._project_path(self.settings.get("rustpotter_model_path", ""))
            if not cli_path or not model_path:
                raise RuntimeError("Не заданы пути Rustpotter.")
            if not os.path.isfile(cli_path):
                raise FileNotFoundError(f"Rustpotter CLI не найден: {cli_path}")
            if not os.path.isfile(model_path):
                raise FileNotFoundError(f"Модель wake word не найдена: {model_path}")
            self.wake_detector = RustpotterWakeWordDetector(
                on_wake=self._on_wake_word_detected,
                cli_path=cli_path,
                model_path=model_path,
                threshold=float(self.settings.get("wake_word_threshold", 0.5)),
                device_index=int(self.settings.get("rustpotter_device_index", 0)),
            )
            self.wake_detector.start()
            self._set_component("wake", True)
            self.after(0, lambda: self.wake_status_label.configure(
                text='Wake word активен • скажите «Джарвис»', text_color=GOOD
            ))
        except Exception as e:
            self._set_component("wake", False)
            print(f"[WakeWord] Не удалось запустить: {e}")
            self.after(0, lambda err=str(e): self.wake_status_label.configure(
                text=f"Wake word недоступен: {err}", text_color=BAD
            ))

    def _project_path(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.join(str(PROJECT_DIR), path)

    def _stop_wake_word(self):
        detector = self.wake_detector
        self.wake_detector = None
        if detector:
            detector.stop()
        self._set_component("wake", False)
        if hasattr(self, "wake_status_label"):
            self.after(0, lambda: self.wake_status_label.configure(
                text="Wake word выключен", text_color=MUTED
            ))

    def _on_wake_word_detected(self):
        if self.models_ready:
            self._set_buttons_enabled(False)
            threading.Thread(target=self._wake_word_listen_and_reply, daemon=True).start()

    def set_status(self, text: str):
        def update():
            self.status_label.configure(text=text)
            low = text.lower()
            if "ошибка" in low:
                color, bg = BAD, "#351c21"
            elif "слуш" in low or "говор" in low:
                color, bg = ACCENT, "#16283b"
            elif "готов" in low:
                color, bg = GOOD, "#173125"
            else:
                color, bg = MUTED, PANEL
            self.status_pill.configure(text=f"  {text.upper()}  ", text_color=color, fg_color=bg)
            self.core_indicator.configure(text_color=color)
        self.after(0, update)

    def _refresh_network_status(self):
        online = is_online(use_cache=False)
        has_key = bool(get_groq_api_key(self.settings))
        if online and has_key:
            text, color = "● Сеть доступна • Groq готов", GOOD
        elif online:
            text, color = "● Сеть доступна • Groq не настроен", WARN
        else:
            text, color = "● Offline • работают локальные функции", BAD
        self.after(0, lambda: self.network_label.configure(text=text, text_color=color))

    def append_log(self, role: str, text: str):
        def _append():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"{role}\n{text}\n\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, _append)

    def _set_buttons_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.after(0, lambda: self.mic_button.configure(state=state))
        self.after(0, lambda: self.send_button.configure(state=state))

    def on_send_text(self):
        text = self.text_entry.get().strip()
        if not text or not self.models_ready:
            return
        self.text_entry.delete(0, "end")
        self.append_log("ВЫ", text)
        self._set_buttons_enabled(False)
        threading.Thread(target=self._process_and_reply, args=(text,), daemon=True).start()

    def on_mic_button(self):
        if self.models_ready:
            self._set_buttons_enabled(False)
            threading.Thread(target=self._listen_and_reply, daemon=True).start()

    def _listen_and_reply(self):
        self.set_status("Слушаю...")
        result = jarvis_voice.listen()
        text = result.get("text", "")
        grammar_text = result.get("grammar_text")
        if not text and not grammar_text:
            self.set_status("Не расслышал")
            self._set_buttons_enabled(True)
            return
        self.append_log("ВЫ • ГОЛОС", text or grammar_text)
        self._process_and_reply(text, grammar_text=grammar_text)

    def _wake_word_listen_and_reply(self):
        self._stop_wake_word()
        try:
            jarvis_voice.play_ack_sound()
            self._listen_and_reply()
        finally:
            if self.models_ready and self.settings.get("wake_word_enabled"):
                self._start_wake_word()

    def _process_and_reply(self, text: str, grammar_text: str | None = None):
        try:
            normalized = jarvis_core.normalize_text(text)
            if "спасибо" in normalized and "джарвис" in normalized:
                self.append_log("JARVIS", "Пожалуйста.")
                jarvis_voice.play_sound(jarvis_voice.SOUND_THANKS)
                return
            self._refresh_network_status()
            self.set_status("Обрабатываю...")
            first_sentence_spoken = threading.Event()

            def _on_speak_ready(sentence: str):
                if not first_sentence_spoken.is_set():
                    first_sentence_spoken.set()
                    self.set_status("Говорю...")
                jarvis_tts.speak(sentence)

            reply = jarvis_core.process_message(
                text, grammar_text=grammar_text, on_speak_ready=_on_speak_ready
            )
            if reply["type"] == "sound":
                self.append_log("JARVIS", "[офлайн — команда не распознана]")
                jarvis_voice.play_sound(reply["path"])
            elif reply["type"] == "local":
                self.append_log("JARVIS", reply["text"])
                jarvis_voice.play_random_ok()
            elif reply["type"] == "streamed":
                self.append_log("JARVIS", reply["text"])
            else:
                self.append_log("JARVIS", reply["text"])
                jarvis_tts.speak(reply["text"])
        except Exception as e:
            self.append_log("ОШИБКА", str(e))
            print(f"[JARVIS] Ошибка обработки: {e}")
        finally:
            self.set_status("Готов к работе")
            self._set_buttons_enabled(True)

    def on_save_settings(self):
        wake_word_was_enabled = self.settings.get("wake_word_enabled")
        if self._groq_key_editing:
            typed_key = self.groq_key_entry.get().strip()
            if typed_key:
                self.settings["groq_api_key"] = typed_key
            elif self.groq_key_entry.cget("placeholder_text") == "Ключ будет удалён после сохранения":
                self.settings["groq_api_key"] = ""
        self.settings["groq_model"] = self.model_entry.get().strip() or "openai/gpt-oss-120b"
        self.settings["xtts_speaker_wav"] = self.voice_wav_entry.get().strip() or "resources/tts/jarvis_voice.wav"
        self.settings["xtts_device"] = self.device_var.get()
        self.settings["xtts_language"] = self.language_entry.get().strip() or "ru"
        self.settings["xtts_playback_padding_ms"] = int(round(self.padding_slider.get()))
        self.settings["xtts_split_sentences"] = bool(self.split_var.get())
        self.settings["wake_word_enabled"] = bool(self.wake_word_var.get())
        save_settings(self.settings)
        jarvis_core.set_groq_model(self.settings["groq_model"])
        jarvis_core.reset_groq_client()
        self._refresh_groq_key_field()
        if self.settings["wake_word_enabled"] and not wake_word_was_enabled:
            self._start_wake_word()
        elif not self.settings["wake_word_enabled"] and wake_word_was_enabled:
            self._stop_wake_word()
        self._set_component("xtts", jarvis_tts.is_configured())
        self._mark_settings_clean()
        self._refresh_network_status()

    def on_close(self):
        self._stop_wake_word()
        self.destroy()
