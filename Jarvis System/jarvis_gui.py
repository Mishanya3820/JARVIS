from jarvis_gui_modern import JarvisModernApp
import customtkinter as ctk


class JarvisApp(JarvisModernApp):
    def __init__(self):
        super().__init__()
        self.save_button = ctk.CTkButton(self.set_frame, text="Сохранить настройки", width=180, height=38, corner_radius=12, command=self.save)
        self.save_button.place(relx=0.98, rely=0.98, anchor="se")


if __name__ == "__main__":
    JarvisApp().mainloop()
