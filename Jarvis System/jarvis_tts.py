"""ElevenLabs TTS для онлайн-ответов JARVIS.

Silero TTS здесь намеренно отсутствует. Офлайн-ответы воспроизводятся
заготовленными WAV-файлами, а динамическая речь генерируется ElevenLabs.
"""

from __future__ import annotations

import io
import os
import threading
import wave

import numpy as np
import sounddevice as sd
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs

from jarvis_settings import (
    get_elevenlabs_api_key,
    get_elevenlabs_voice_id,
    load_settings,
)


_client: ElevenLabs | None = None
_client_lock = threading.Lock()


def _get_client() -> ElevenLabs:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                api_key = get_elevenlabs_api_key()
                if not api_key:
                    raise RuntimeError(
                        "Не найден ELEVENLABS_API_KEY. "
                        "Задай его как переменную окружения Windows."
                    )
                _client = ElevenLabs(api_key=api_key)
    return _client


def _get_voice_id() -> str:
    voice_id = get_elevenlabs_voice_id()
    if not voice_id:
        raise RuntimeError(
            "Не задан ELEVENLABS_VOICE_ID. "
            "Выбери голос ElevenLabs и укажи его ID."
        )
    return voice_id


def _pcm_bytes_to_numpy(data: bytes, sample_rate: int = 44100) -> np.ndarray:
    """Преобразует PCM S16LE из ElevenLabs в float32 для sounddevice."""
    if not data:
        return np.empty(0, dtype=np.float32)
    audio = np.frombuffer(data, dtype=np.int16)
    return audio.astype(np.float32) / 32768.0


def speak(text: str) -> None:
    """Генерирует и воспроизводит естественную речь ElevenLabs."""
    text = (text or "").strip()
    if not text:
        return

    settings = load_settings()
    client = _get_client()
    voice_id = _get_voice_id()

    response = client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
        model_id=settings.get("elevenlabs_model", "eleven_multilingual_v2"),
        output_format="mp3_44100_128",
        voice_settings=VoiceSettings(
            stability=float(settings.get("elevenlabs_stability", 0.48)),
            similarity_boost=float(settings.get("elevenlabs_similarity", 0.82)),
            style=float(settings.get("elevenlabs_style", 0.12)),
            use_speaker_boost=bool(settings.get("elevenlabs_speaker_boost", True)),
            speed=float(settings.get("elevenlabs_speed", 0.96)),
        ),
    )

    # SDK может вернуть bytes или итерируемый поток bytes.
    if isinstance(response, (bytes, bytearray)):
        audio_bytes = bytes(response)
    else:
        audio_bytes = b"".join(chunk for chunk in response if chunk)

    audio = _pcm_bytes_to_numpy(audio_bytes, 44100)
    if audio.size == 0:
        raise RuntimeError("ElevenLabs вернул пустой аудиопоток.")

    sd.play(audio, samplerate=44100)
    sd.wait()


def is_configured() -> bool:
    return bool(get_elevenlabs_api_key() and get_elevenlabs_voice_id())
