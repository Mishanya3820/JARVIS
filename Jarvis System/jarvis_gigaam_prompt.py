from __future__ import annotations


def ask_install() -> bool:
    """Show a Windows confirmation dialog before downloading GigaAM."""
    import ctypes

    result = ctypes.windll.user32.MessageBoxW(
        None,
        "GigaAM STT не установлен.\n\n"
        "JARVIS может автоматически скачать runtime и модель GigaAM v3 "
        "(примерно 320 МБ).\n\n"
        "Установить сейчас?",
        "JARVIS — GigaAM STT",
        0x00000004 | 0x00000020 | 0x00010000,
    )
    return result == 6
