import os
import threading
import tkinter as tk
 
import customtkinter as ctk
 
import jarvis_core
import jarvis_tts
import jarvis_voice
from jarvis_network import is_online
from jarvis_settings import (
    get_groq_api_key,
    load_settings,
    save_settings,
    set_groq_api_key,
)
 
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
 
 
class JarvisApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("JARVIS")
        self.geometry("700x760")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
 
        self.settings = load_settings()
        self.models_ready = False
        self.wake_detector = None
        self.settings_dirty = False
        self._settings_tracking_ready = False
        self._groq_key_editing = False
 
        self._build_ui()
        self._setup_settings_change_tracking()
 
        # Первый запуск: если ключ не задан ни в Windows, ни в settings.json,
        # предлагаем добавить его прямо из JARVIS.
        self.after(250, self._show_first_run_groq_setup)
        threading.Thread(target=self._load_models_thread, daemon=True).start()
 
    def _build_ui(self):
        self.tabview = ctk.CTkTabview(self, width=680, height=730)
        self.tabview.pack(padx=10, pady=10, fill="both", expand=True)
        self.tab_main = self.tabview.add("JARVIS")
        self.tab_settings = self.tabview.add("Настройки")
        self._build_main_tab()
        self._build_settings_tab()
 
    def _build_main_tab(self):
        tab = self.tab_main
        self.status_label = ctk.CTkLabel(tab, text="Загрузка...", font=ctk.CTkFont(size=16, weight="bold"))
        self.status_label.pack(pady=(10, 5))
        self.network_label = ctk.CTkLabel(tab, text="", text_color="gray")
        self.network_label.pack(pady=(0, 5))
        self.log_box = ctk.CTkTextbox(tab, width=640, height=360, wrap="word")
        self.log_box.pack(padx=10, pady=10, fill="both", expand=True)
        self.log_box.configure(state="disabled")
 
        input_frame = ctk.CTkFrame(tab, fg_color="transparent")
        input_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.text_entry = ctk.CTkEntry(input_frame, placeholder_text="Напишите команду...")
        self.text_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.text_entry.bind("<Return>", lambda event: self.on_send_text())
        self.send_button = ctk.CTkButton(input_frame, text="Отправить", width=100, command=self.on_send_text)
        self.send_button.pack(side="left")
        self.mic_button = ctk.CTkButton(tab, text="🎤 Голосовая команда", height=50, command=self.on_mic_button, state="disabled")
        self.mic_button.pack(padx=10, pady=(0, 5), fill="x")
        self.wake_status_label = ctk.CTkLabel(tab, text="", text_color="gray")
        self.wake_status_label.pack(pady=(0, 10))
 
    def _build_settings_tab(self):
        tab = self.tab_settings
 
        # Баннер несохранённых изменений.
        self.unsaved_banner = ctk.CTkFrame(tab, fg_color=("#fff3cd", "#4a3b12"), corner_radius=8)
        self.unsaved_banner.pack(fill="x", padx=10, pady=(10, 8))
        banner_label = ctk.CTkLabel(
            self.unsaved_banner,
            text="⚠ Настройки не сохранены",
            text_color=("#664d03", "#ffd966"),
            font=ctk.CTkFont(weight="bold"),
        )
        banner_label.pack(side="left", padx=12, pady=8)
        ctk.CTkButton(
            self.unsaved_banner,
            text="Сохранить",
            width=110,
            height=30,
            command=self.on_save_settings,
        ).pack(side="right", padx=8, pady=6)
        self.unsaved_banner.pack_forget()
 
        note = ctk.CTkLabel(
            tab,
            text=(
                "Онлайн: Groq + ElevenLabs.\n"
                "Офлайн: локальные команды и готовые WAV.\n"
                "Ключ Groq хранится локально и в интерфейсе показывается точками."
            ),
            justify="left", text_color="gray",
        )
        note.pack(anchor="w", padx=10, pady=(5, 15))
 
        self._label(tab, "API-ключ Groq:")
        groq_key_frame = ctk.CTkFrame(tab, fg_color="transparent")
        groq_key_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.groq_key_entry = ctk.CTkEntry(groq_key_frame, show="•", placeholder_text="Введите API-ключ Groq")
        self.groq_key_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.groq_key_entry.bind("<FocusIn>", self._on_groq_key_focus_in)
        self.groq_key_entry.bind("<FocusOut>", self._on_groq_key_focus_out)
        ctk.CTkButton(groq_key_frame, text="Удалить", width=90, command=self._clear_groq_key).pack(side="right")
        self._refresh_groq_key_field()
 
        self._label(tab, "Модель Groq:")
        self.model_entry = ctk.CTkEntry(tab)
        self.model_entry.insert(0, self.settings["groq_model"])
        self.model_entry.pack(fill="x", padx=10, pady=(0, 10))
 
        self._label(tab, "Модель ElevenLabs:")
        self.tts_model_entry = ctk.CTkEntry(tab)
        self.tts_model_entry.insert(0, self.settings.get("elevenlabs_model", "eleven_multilingual_v2"))
        self.tts_model_entry.pack(fill="x", padx=10, pady=(0, 10))
 
        self._label(tab, "Voice ID ElevenLabs:")
        self.voice_id_entry = ctk.CTkEntry(tab, placeholder_text="Voice ID из Voice Library")
        self.voice_id_entry.insert(0, self.settings.get("elevenlabs_voice_id", ""))
        self.voice_id_entry.pack(fill="x", padx=10, pady=(0, 10))
 
        for key, label, attr, default in [
            ("elevenlabs_stability", "Stability", "stability_slider", 0.48),
            ("elevenlabs_similarity", "Similarity", "similarity_slider", 0.82),
            ("elevenlabs_style", "Style", "style_slider", 0.12),
        ]:
            self._label(tab, label + ":")
            slider = ctk.CTkSlider(tab, from_=0, to=1, number_of_steps=100)
            slider.set(self.settings.get(key, default))
            slider.pack(fill="x", padx=10, pady=(0, 8))
            setattr(self, attr, slider)
 
        self._label(tab, "Скорость:")
        self.speed_slider = ctk.CTkSlider(tab, from_=0.7, to=1.2, number_of_steps=50)
        self.speed_slider.set(self.settings.get("elevenlabs_speed", 0.96))
        self.speed_slider.pack(fill="x", padx=10, pady=(0, 8))
 
        self.boost_var = tk.BooleanVar(value=self.settings.get("elevenlabs_speaker_boost", True))
        ctk.CTkCheckBox(tab, text="Speaker Boost", variable=self.boost_var).pack(anchor="w", padx=10, pady=(0, 8))
 
        self.wake_word_var = tk.BooleanVar(value=self.settings.get("wake_word_enabled", True))
        ctk.CTkCheckBox(tab, text='Реагировать на "Джарвис" без кнопки', variable=self.wake_word_var).pack(anchor="w", padx=10, pady=(0, 12))
 
        ctk.CTkButton(tab, text="Сохранить настройки", command=self.on_save_settings).pack(pady=8)
        self.settings_status_label = ctk.CTkLabel(tab, text="", text_color="lightgreen")
        self.settings_status_label.pack()
 
    def _setup_settings_change_tracking(self):
        """Подключает отслеживание любых изменений в настройках."""
        for entry in (self.model_entry, self.tts_model_entry, self.voice_id_entry):
            entry.bind("<KeyRelease>", lambda event: self._mark_settings_dirty(), add="+")
 
        self.groq_key_entry.bind("<KeyRelease>", lambda event: self._mark_settings_dirty(), add="+")
 
        for slider in (self.stability_slider, self.similarity_slider, self.style_slider, self.speed_slider):
            slider.configure(command=lambda value: self._mark_settings_dirty())
 
        self.boost_var.trace_add("write", lambda *_: self._mark_settings_dirty())
        self.wake_word_var.trace_add("write", lambda *_: self._mark_settings_dirty())
        self._settings_tracking_ready = True
 
    def _mark_settings_dirty(self):
        if not self._settings_tracking_ready:
            return
        if not self.settings_dirty:
            self.settings_dirty = True
            self.unsaved_banner.pack(fill="x", padx=10, pady=(10, 8), before=self.tab_settings.winfo_children()[1])
        self.settings_status_label.configure(text="Есть несохранённые изменения.", text_color="#ffd966")
 
    def _mark_settings_clean(self):
        self.settings_dirty = False
        self.unsaved_banner.pack_forget()
        self.settings_status_label.configure(text="Настройки сохранены.", text_color="lightgreen")
 
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
            self.groq_key_entry.configure(placeholder_text="Введите API-ключ Groq")
 
    def _on_groq_key_focus_in(self, _event=None):
        if not self._groq_key_editing:
            self._groq_key_editing = True
            self.groq_key_entry.delete(0, "end")
            self.groq_key_entry.configure(placeholder_text="Введите новый API-ключ")
 
    def _on_groq_key_focus_out(self, _event=None):
        if self._groq_key_editing and not self.groq_key_entry.get().strip():
            # Пустое поле само по себе не удаляет ключ, пока пользователь
            # явно не нажмёт «Удалить» и не сохранит настройки.
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
            dialog,
            text="Добро пожаловать в JARVIS",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(pady=(24, 8))
        ctk.CTkLabel(
            dialog,
            text="Для онлайн-ответов JARVIS нужен API-ключ Groq.\n"
                 "Его можно добавить сейчас или сделать это позже в настройках.",
            justify="center",
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
 
        def skip():
            dialog.destroy()
 
        ctk.CTkButton(buttons, text="Сохранить", command=save_first_key).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(buttons, text="Пропустить", command=skip, fg_color="gray").pack(side="right", expand=True, padx=5)
 
    def _label(self, parent, text):
        ctk.CTkLabel(parent, text=text, anchor="w").pack(fill="x", padx=10, pady=(0, 4))
 
    def _load_models_thread(self):
        try:
            self.set_status("Загружаю Vosk...")
            jarvis_voice.get_vosk_model()
            self.set_status("Проверяю сеть...")
            self._refresh_network_status()
            if is_online() and get_groq_api_key(self.settings):
                try:
                    self.set_status("Проверяю связь с Groq...")
                    jarvis_core.warmup()
                except Exception as e:
                    print(f"[Предупреждение] Groq недоступна: {e}")
            elif is_online():
                print("[JARVIS] Groq API-ключ не задан. Онлайн-ответы отключены.")
 
            self.models_ready = True
            self.set_status("Готов к работе")
            self.after(0, lambda: self.mic_button.configure(state="normal"))
            jarvis_voice.play_sound(jarvis_voice.SOUND_RUN)
            if self.settings.get("wake_word_enabled"):
                self._start_wake_word()
        except Exception as e:
            self.set_status(f"Ошибка загрузки: {e}")
            print(f"[JARVIS] Ошибка запуска: {e}")
 
    # -------------------- Rustpotter --------------------
 
    def _start_wake_word(self):
        try:
            from jarvis_wakeword import RustpotterWakeWordDetector
            cli_path = self.settings.get("rustpotter_cli_path", "")
            model_path = self.settings.get("rustpotter_model_path", "")
            if not cli_path or not model_path:
                raise RuntimeError("Не заданы пути Rustpotter.")
 
            cli_path = self._project_path(cli_path)
            model_path = self._project_path(model_path)
            if not os.path.isfile(cli_path):
                raise FileNotFoundError(f"Rustpotter CLI не найден: {cli_path}")
            if not os.path.isfile(model_path):
                raise FileNotFoundError(f"Модель wake word не найдена: {model_path}")
 
            self.wake_detector = RustpotterWakeWordDetector(
                on_wake=self._on_wake_word_detected,
                cli_path=cli_path,
                model_path=model_path,
                threshold=float(self.settings.get("wake_word_threshold", 0.5)),
            )
            self.wake_detector.start()
            self.after(0, lambda: self.wake_status_label.configure(text='Слушаю фоном: скажите "Джарвис"'))
        except Exception as e:
            print(f"[WakeWord] Не удалось запустить: {e}")
            self.after(0, lambda err=str(e): self.wake_status_label.configure(text=f"Wake word недоступен: {err}"))
 
    def _project_path(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(project_dir, path)
 
    def _stop_wake_word(self):
        detector = self.wake_detector
        self.wake_detector = None
        if detector:
            detector.stop()
        if hasattr(self, "wake_status_label"):
            self.after(0, lambda: self.wake_status_label.configure(text=""))
 
    def _on_wake_word_detected(self):
        if self.models_ready:
            self.after(0, lambda: self._set_buttons_enabled(False))
            threading.Thread(target=self._wake_word_listen_and_reply, daemon=True).start()
 
    # -------------------- GUI helpers --------------------
 
    def set_status(self, text: str):
        self.after(0, lambda: self.status_label.configure(text=text))
 
    def _refresh_network_status(self):
        online = is_online(use_cache=False)
        has_key = bool(get_groq_api_key(self.settings))
        if online and has_key:
            text = "🟢 Сеть доступна"
            color = "lightgreen"
        elif online:
            text = "🟡 Сеть доступна, но Groq API-ключ не задан"
            color = "#ffd966"
        else:
            text = "🔴 Нет сети - только локальные команды"
            color = "orange"
        self.after(0, lambda: self.network_label.configure(text=text, text_color=color))
 
    def append_log(self, role: str, text: str):
        def _append():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"{role}: {text}\n\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, _append)
 
    def _set_buttons_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.after(0, lambda: self.mic_button.configure(state=state))
        self.after(0, lambda: self.send_button.configure(state=state))
 
    # -------------------- Input --------------------
 
    def on_send_text(self):
        text = self.text_entry.get().strip()
        if not text or not self.models_ready:
            return
        self.text_entry.delete(0, "end")
        self.append_log("Вы", text)
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
 
        # Показываем пользователю свободный текст (он информативнее),
        # но для поиска локальной команды приоритет у grammar_text —
        # см. jarvis_core.match_local_command.
        self.append_log("Вы (голосом)", text or grammar_text)
        self._process_and_reply(text, grammar_text=grammar_text)
 
    def _wake_word_listen_and_reply(self):
        self._stop_wake_word()
        try:
            jarvis_voice.play_ack_sound()
            self._listen_and_reply()
        finally:
            if self.models_ready and self.settings.get("wake_word_enabled"):
                self._start_wake_word()
 
    # -------------------- Processing --------------------
 
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
            self.append_log("Ошибка", str(e))
            print(f"[JARVIS] Ошибка обработки: {e}")
        finally:
            self.set_status("Готов к работе")
            self._set_buttons_enabled(True)
 
    # -------------------- Settings --------------------
 
    def on_save_settings(self):
        wake_word_was_enabled = self.settings.get("wake_word_enabled")
 
        if self._groq_key_editing:
            typed_key = self.groq_key_entry.get().strip()
            if typed_key:
                self.settings["groq_api_key"] = typed_key
            elif self.groq_key_entry.cget("placeholder_text") == "Ключ будет удалён после сохранения":
                self.settings["groq_api_key"] = ""
 
        self.settings["groq_model"] = self.model_entry.get().strip() or "llama-3.3-70b-versatile"
        self.settings["elevenlabs_model"] = self.tts_model_entry.get().strip() or "eleven_multilingual_v2"
        self.settings["elevenlabs_voice_id"] = self.voice_id_entry.get().strip()
        self.settings["elevenlabs_stability"] = round(self.stability_slider.get(), 2)
        self.settings["elevenlabs_similarity"] = round(self.similarity_slider.get(), 2)
        self.settings["elevenlabs_style"] = round(self.style_slider.get(), 2)
        self.settings["elevenlabs_speed"] = round(self.speed_slider.get(), 2)
        self.settings["elevenlabs_speaker_boost"] = bool(self.boost_var.get())
        self.settings["wake_word_enabled"] = bool(self.wake_word_var.get())
        save_settings(self.settings)
 
        jarvis_core.set_groq_model(self.settings["groq_model"])
        jarvis_core.reset_groq_client()
        self._refresh_groq_key_field()
 
        if self.settings["wake_word_enabled"] and not wake_word_was_enabled:
            self._start_wake_word()
        elif not self.settings["wake_word_enabled"] and wake_word_was_enabled:
            self._stop_wake_word()
 
        self._mark_settings_clean()
        self._refresh_network_status()
 
    def on_close(self):
        self._stop_wake_word()
        try:
            jarvis_voice.play_sound(jarvis_voice.SOUND_OFF)
        finally:
            self.destroy()
 
 
if __name__ == "__main__":
    app = JarvisApp()
    app.mainloop()