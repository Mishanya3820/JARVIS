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

BG="#080b10"; PANEL="#10151d"; PANEL2="#151b24"; BORDER="#252d38"; ACCENT="#4aa8ff"; TEXT="#edf2f7"; MUTED="#7f8b99"; GOOD="#55d187"; WARN="#ffd166"; BAD="#ff6b6b"
MODES={"performance":("Производительный","Максимальная скорость"),"balanced":("Сбалансированный","Рекомендуемый баланс"),"economy":("Экономичный","Минимальная нагрузка")}
ENGINES={"coqui":"Coqui XTTS-v2","elevenlabs":"ElevenLabs","silero":"Silero TTS"}

class JarvisModernApp(ctk.CTk):
    def __init__(self):
        super().__init__(); self.title("JARVIS"); self.geometry("1050x720"); self.minsize(900,620); self.configure(fg_color=BG); self.protocol("WM_DELETE_WINDOW",self.on_close)
        self.settings=load_settings(); self.models_ready=False; self.wake_detector=None; self.dirty=False; self._pulse=0
        self.build(); self.after(250,self.first_run); threading.Thread(target=self.load_models,daemon=True).start(); self.animate()

    def build(self):
        self.grid_columnconfigure(1,weight=1); self.grid_rowconfigure(0,weight=1)
        side=ctk.CTkFrame(self,width=220,corner_radius=0,fg_color=PANEL); side.grid(row=0,column=0,sticky="nsew"); side.grid_propagate(False)
        ctk.CTkLabel(side,text="JARVIS",text_color=TEXT,font=ctk.CTkFont(size=28,weight="bold")).pack(anchor="w",padx=22,pady=(28,2)); ctk.CTkLabel(side,text="LOCAL AI SYSTEM",text_color=ACCENT,font=ctk.CTkFont(size=10,weight="bold")).pack(anchor="w",padx=22,pady=(0,25))
        self.nb=ctk.CTkButton(side,text="⌂  Система",anchor="w",command=self.main,fg_color="#1c2734",hover_color=PANEL2); self.nb.pack(fill="x",padx=12,pady=4)
        self.ns=ctk.CTkButton(side,text="⚙  Настройки",anchor="w",command=self.settings_page,fg_color="transparent",hover_color=PANEL2); self.ns.pack(fill="x",padx=12,pady=4)
        ctk.CTkFrame(side,height=1,fg_color=BORDER).pack(fill="x",padx=18,pady=20)
        ctk.CTkLabel(side,text="СОСТОЯНИЕ",text_color=MUTED,font=ctk.CTkFont(size=10,weight="bold")).pack(anchor="w",padx=22,pady=(0,8)); self.dots={}
        for k,n in (("gigaAM","GigaAM STT"),("wake","Wake word"),("local","Local commands"),("groq","Groq"),("xtts","TTS")):
            r=ctk.CTkFrame(side,fg_color="transparent"); r.pack(fill="x",padx=22,pady=3); ctk.CTkLabel(r,text=n,text_color=MUTED).pack(side="left",fill="x",expand=True); d=ctk.CTkLabel(r,text="●",text_color="#39414d",width=18); d.pack(side="right"); self.dots[k]=d
        ctk.CTkLabel(side,text="Offline-first • Windows",text_color=MUTED,font=ctk.CTkFont(size=10)).pack(side="bottom",anchor="w",padx=22,pady=20)
        self.content=ctk.CTkFrame(self,fg_color=BG); self.content.grid(row=0,column=1,sticky="nsew",padx=18,pady=18); self.content.grid_columnconfigure(0,weight=1); self.content.grid_rowconfigure(0,weight=1)
        self.main_frame=ctk.CTkFrame(self.content,fg_color="transparent"); self.set_frame=ctk.CTkFrame(self.content,fg_color="transparent"); self.main_frame.grid(row=0,column=0,sticky="nsew"); self.set_frame.grid(row=0,column=0,sticky="nsew"); self.set_frame.grid_remove(); self.build_main(); self.build_settings()
        self.toast=ctk.CTkLabel(self, text="✓  Настройки сохранены", fg_color="#173125", text_color=GOOD, corner_radius=14,font=ctk.CTkFont(size=12,weight="bold"))

    def build_main(self):
        p=self.main_frame; p.grid_columnconfigure(0,weight=1); p.grid_rowconfigure(2,weight=1)
        h=ctk.CTkFrame(p,fg_color="transparent"); h.grid(row=0,column=0,sticky="ew",pady=(0,14)); h.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(h,text="Система JARVIS",text_color=TEXT,font=ctk.CTkFont(size=25,weight="bold")).grid(row=0,column=0,sticky="w"); self.net=ctk.CTkLabel(h,text="Проверка сети...",text_color=MUTED); self.net.grid(row=1,column=0,sticky="w"); self.status=ctk.CTkLabel(h,text="  ЗАГРУЗКА  ",fg_color=PANEL,text_color=MUTED,corner_radius=16); self.status.grid(row=0,column=1,rowspan=2,sticky="e")
        hero=ctk.CTkFrame(p,fg_color=PANEL,corner_radius=18,border_width=1,border_color=BORDER); hero.grid(row=1,column=0,sticky="ew",pady=(0,14)); hero.grid_columnconfigure(1,weight=1)
        self.core=ctk.CTkLabel(hero,text="J",width=100,height=100,corner_radius=50,fg_color="#16283b",text_color=ACCENT,font=ctk.CTkFont(size=42,weight="bold")); self.core.grid(row=0,column=0,rowspan=2,padx=28,pady=24)
        ctk.CTkLabel(hero,text="CENTRAL INTELLIGENCE",text_color=MUTED).grid(row=0,column=1,sticky="sw"); self.status_text=ctk.CTkLabel(hero,text="Загрузка компонентов...",text_color=TEXT,font=ctk.CTkFont(size=20,weight="bold")); self.status_text.grid(row=1,column=1,sticky="nw",pady=(3,24)); self.wake_text=ctk.CTkLabel(hero,text="Wake word: инициализация...",text_color=MUTED); self.wake_text.grid(row=0,column=2,padx=28,pady=22)
        self.log=ctk.CTkTextbox(p,fg_color=PANEL,border_width=1,border_color=BORDER,corner_radius=14); self.log.grid(row=2,column=0,sticky="nsew",pady=(0,14)); self.log.configure(state="disabled")
        row=ctk.CTkFrame(p,fg_color="transparent"); row.grid(row=3,column=0,sticky="ew"); row.grid_columnconfigure(0,weight=1); self.entry=ctk.CTkEntry(row,height=46,corner_radius=12,fg_color=PANEL,border_color=BORDER,placeholder_text="Введите команду или вопрос..."); self.entry.grid(row=0,column=0,sticky="ew",padx=(0,8)); self.entry.bind("<Return>",lambda e:self.send()); self.sendbtn=ctk.CTkButton(row,text="➤",width=54,height=46,command=self.send); self.sendbtn.grid(row=0,column=1,padx=(0,8)); self.mic=ctk.CTkButton(row,text="🎙",width=54,height=46,command=self.mic_input,state="disabled"); self.mic.grid(row=0,column=2)

    def build_settings(self):
        p=self.set_frame; p.grid_columnconfigure(0,weight=1); p.grid_rowconfigure(1,weight=1); ctk.CTkLabel(p,text="Настройки",text_color=TEXT,font=ctk.CTkFont(size=25,weight="bold")).grid(row=0,column=0,sticky="w",pady=(0,14))
        s=ctk.CTkScrollableFrame(p,fg_color=PANEL,corner_radius=16,border_width=1,border_color=BORDER); s.grid(row=1,column=0,sticky="nsew")
        self.section(s,"РЕЖИМ РАБОТЫ"); self.mode=tk.StringVar(value=self.settings.get("performance_mode","balanced")); ctk.CTkOptionMenu(s,variable=self.mode,values=list(MODES),command=lambda _:self.dirty_on()).pack(anchor="w",padx=4); ctk.CTkLabel(s,text="Модели не выгружаются автоматически.",text_color=MUTED).pack(anchor="w",padx=4,pady=(5,15))
        self.section(s,"ОНЛАЙН-ОТВЕТЫ"); self.label(s,"API-ключ Groq"); self.groq=ctk.CTkEntry(s,show="•",placeholder_text="Введите API-ключ"); self.groq.pack(fill="x",padx=4,pady=(0,10)); self.refresh_key(self.groq,"groq_api_key","GROQ_API_KEY"); self.label(s,"Модель Groq"); self.gmodel=ctk.CTkEntry(s); self.gmodel.insert(0,self.settings["groq_model"]); self.gmodel.pack(fill="x",padx=4,pady=(0,18))
        self.section(s,"ГОЛОС JARVIS"); card=ctk.CTkFrame(s,fg_color=PANEL2,corner_radius=14); card.pack(fill="x",padx=4,pady=(0,18)); top=ctk.CTkFrame(card,fg_color="transparent"); top.pack(fill="x",padx=14,pady=12); ctk.CTkLabel(top,text="Движок озвучки",text_color=TEXT,font=ctk.CTkFont(weight="bold")).pack(side="left"); self.engine=tk.StringVar(value=self.settings.get("tts_engine","coqui")); ctk.CTkOptionMenu(top,variable=self.engine,values=list(ENGINES),command=lambda _:self.switch_tts()).pack(side="right"); self.hint=ctk.CTkLabel(card,text="",text_color=MUTED,wraplength=700,justify="left"); self.hint.pack(fill="x",padx=14,pady=(0,8)); self.panels={}; self.make_coqui(card); self.make_eleven(card); self.make_silero(card); self.switch_tts()
        self.section(s,"WAKE WORD"); self.wake=tk.BooleanVar(value=bool(self.settings.get("wake_word_enabled",True))); ctk.CTkCheckBox(s,text="Включить wake word «Джарвис»",variable=self.wake,command=self.dirty_on).pack(anchor="w",padx=4,pady=(0,20))

    def section(self,p,t): ctk.CTkLabel(p,text=t,text_color=ACCENT,font=ctk.CTkFont(size=11,weight="bold")).pack(anchor="w",padx=4,pady=(8,10))
    def label(self,p,t): ctk.CTkLabel(p,text=t,text_color=MUTED).pack(anchor="w",padx=4,pady=(0,4))
    def dirty_on(self,*a): self.dirty=True
    def panel(self,k,p): self.panels[k]=p; p.pack_forget()

    def make_coqui(self,parent):
        p=ctk.CTkFrame(parent,fg_color="transparent"); self.panel("coqui",p); self.label(p,"Reference WAV"); self.cwav=ctk.CTkEntry(p); self.cwav.insert(0,self.settings.get("xtts_speaker_wav","resources/tts/jarvis_voice.wav")); self.cwav.pack(fill="x",pady=(0,10)); self.label(p,"Устройство"); self.cdev=tk.StringVar(value=self.settings.get("xtts_device","cpu")); ctk.CTkOptionMenu(p,variable=self.cdev,values=["cpu","cuda"]).pack(anchor="w",pady=(0,10)); self.label(p,"Язык"); self.clang=ctk.CTkEntry(p); self.clang.insert(0,self.settings.get("xtts_language","ru")); self.clang.pack(fill="x",pady=(0,10)); self.csplit=tk.BooleanVar(value=bool(self.settings.get("xtts_split_sentences",True))); ctk.CTkCheckBox(p,text="Разбивать длинные ответы на предложения",variable=self.csplit,command=self.dirty_on).pack(anchor="w",pady=(0,6))
    def make_eleven(self,parent):
        p=ctk.CTkFrame(parent,fg_color="transparent"); self.panel("elevenlabs",p); self.label(p,"API-ключ ElevenLabs"); self.ekey=ctk.CTkEntry(p,show="•",placeholder_text="Ключ ElevenLabs"); self.ekey.pack(fill="x",pady=(0,10)); self.refresh_key(self.ekey,"elevenlabs_api_key","ELEVENLABS_API_KEY"); self.label(p,"Voice ID"); self.evoice=ctk.CTkEntry(p); self.evoice.insert(0,self.settings.get("elevenlabs_voice_id","")); self.evoice.pack(fill="x",pady=(0,10)); self.label(p,"Модель"); self.emodel=tk.StringVar(value=self.settings.get("elevenlabs_model","eleven_multilingual_v2")); ctk.CTkOptionMenu(p,variable=self.emodel,values=["eleven_multilingual_v2","eleven_flash_v2_5"]).pack(anchor="w",pady=(0,6))
    def make_silero(self,parent):
        p=ctk.CTkFrame(parent,fg_color="transparent"); self.panel("silero",p); self.label(p,"Голос"); self.speaker=tk.StringVar(value=self.settings.get("silero_speaker","eugene")); ctk.CTkOptionMenu(p,variable=self.speaker,values=["eugene","aidar","baya","kseniya","xenia"]).pack(anchor="w",pady=(0,10)); self.label(p,"Устройство"); self.sdev=tk.StringVar(value=self.settings.get("silero_device","cpu")); ctk.CTkOptionMenu(p,variable=self.sdev,values=["cpu","cuda"]).pack(anchor="w",pady=(0,10)); self.label(p,"Частота"); self.srate=tk.StringVar(value=str(self.settings.get("silero_sample_rate",48000))); ctk.CTkOptionMenu(p,variable=self.srate,values=["24000","48000"]).pack(anchor="w",pady=(0,6))

    def switch_tts(self,*a):
        for p in self.panels.values(): p.pack_forget()
        k=self.engine.get(); self.panels.get(k,self.panels["coqui"]).pack(fill="x",padx=14,pady=(0,12)); self.hint.configure(text={"coqui":"Coqui XTTS-v2 — локальное клонирование голоса.","elevenlabs":"ElevenLabs — облачная озвучка через API.","silero":"Silero TTS — быстрая локальная озвучка с готовыми голосами."}.get(k,"")); self.dirty_on()

    def refresh_key(self,e,setting,env):
        val=(self.settings.get(setting) or os.environ.get(env,"")).strip(); e.delete(0,"end");
        if val: e.insert(0,"•"*16)

    def save(self):
        self.settings.update({"performance_mode":self.mode.get(),"groq_model":self.gmodel.get().strip(),"tts_engine":self.engine.get(),"xtts_speaker_wav":self.cwav.get().strip(),"xtts_device":self.cdev.get(),"xtts_language":self.clang.get().strip() or "ru","xtts_split_sentences":bool(self.csplit.get()),"elevenlabs_voice_id":self.evoice.get().strip(),"elevenlabs_model":self.emodel.get(),"silero_speaker":self.speaker.get(),"silero_device":self.sdev.get(),"silero_sample_rate":int(self.srate.get()),"wake_word_enabled":bool(self.wake.get())})
        save_settings(self.settings); jarvis_core.set_groq_model(self.settings["groq_model"]); jarvis_core.reset_groq_client(); self.dirty=False; self.toast.place(relx=.98,rely=.94,anchor="se"); self.after(2200,self.toast.place_forget)

    def main(self): self.set_frame.grid_remove(); self.main_frame.grid(); self.nb.configure(fg_color="#1c2734"); self.ns.configure(fg_color="transparent")
    def settings_page(self): self.main_frame.grid_remove(); self.set_frame.grid(); self.nb.configure(fg_color="transparent"); self.ns.configure(fg_color="#1c2734")
    def status_set(self,t): self.after(0,lambda:self.status_text.configure(text=t))
    def dot(self,k,v): self.after(0,lambda:self.dots[k].configure(text_color=GOOD if v else BAD))

    def load_models(self):
        try:
            self.status_set("Загружаю модели..."); jarvis_voice.warmup_voice_models(); self.dot("gigaAM",True)
            try: jarvis_tts.warmup(); self.dot("xtts",jarvis_tts.is_configured())
            except Exception as e: print("[TTS]",e); self.dot("xtts",False)
            self.dot("local",True); self.after(0,lambda:self.mic.configure(state="normal")); self.models_ready=True; self.status_set("Готов к работе"); jarvis_voice.play_sound(jarvis_voice.SOUND_RUN)
            if self.settings.get("wake_word_enabled"): self.start_wake()
        except Exception as e: self.status_set(f"Ошибка загрузки: {e}"); self.dot("gigaAM",False)

    def start_wake(self):
        try:
            from jarvis_wakeword import RustpotterWakeWordDetector
            cli=self.path(self.settings.get("rustpotter_cli_path","")); model=self.path(self.settings.get("rustpotter_model_path","")); self.wake_detector=RustpotterWakeWordDetector(on_wake=self.wake_detect,cli_path=cli,model_path=model,threshold=float(self.settings.get("wake_word_threshold",.5)),device_index=int(self.settings.get("rustpotter_device_index",0))); self.wake_detector.start(); self.dot("wake",True)
        except Exception as e: print("[WakeWord]",e); self.dot("wake",False)
    def path(self,p): return p if os.path.isabs(p) else os.path.join(str(PROJECT_DIR),p)
    def wake_detect(self):
        if self.models_ready: threading.Thread(target=self.voice_reply,daemon=True).start()
    def voice_reply(self):
        self.mic.configure(state="disabled"); self._stop_wake(); jarvis_voice.play_ack_sound(); r=jarvis_voice.listen(); t=r.get("text",""); g=r.get("grammar_text");
        if t or g: self.process(t,g)
        else: self.mic.configure(state="normal"); self.start_wake()
    def _stop_wake(self):
        if self.wake_detector: self.wake_detector.stop(); self.wake_detector=None
    def send(self):
        t=self.entry.get().strip(); self.entry.delete(0,"end")
        if t and self.models_ready: self.process(t)
    def mic_input(self): threading.Thread(target=self.voice_reply,daemon=True).start()
    def process(self,text,grammar=None):
        try:
            r=jarvis_core.process_message(text,grammar_text=grammar,on_speak_ready=lambda x:jarvis_tts.speak(x))
            self.log_add("ВЫ",text); self.log_add("JARVIS",r.get("text", ""))
            if r["type"]=="sound": jarvis_voice.play_sound(r["path"])
            elif r["type"]=="local": jarvis_voice.play_random_ok()
            elif r["type"]!="streamed": jarvis_tts.speak(r["text"])
        except Exception as e: self.log_add("ОШИБКА",str(e))
        finally: self.after(0,lambda:self.mic.configure(state="normal"))
    def log_add(self,a,b):
        self.after(0,lambda:(self.log.configure(state="normal"),self.log.insert("end",f"{a}\n{b}\n\n"),self.log.see("end"),self.log.configure(state="disabled")))
    def first_run(self): pass
    def animate(self):
        self._pulse=(self._pulse+1)%20
        if self.models_ready: self.core.configure(width=102 if self._pulse in (0,1,19) else 100,height=102 if self._pulse in (0,1,19) else 100)
        self.after(120,self.animate)
    def on_close(self):
        try: self._stop_wake(); jarvis_voice.play_sound(jarvis_voice.SOUND_OFF)
        except Exception: pass
        self.destroy()

if __name__=="__main__":
    JarvisModernApp().mainloop()
