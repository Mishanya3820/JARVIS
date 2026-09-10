import json
import os
import random
import threading
import warnings
import wave

import numpy as np
import sounddevice as sd

from jarvis_paths import PROJECT_DIR, RESOURCES_DIR

SAMPLE_RATE = 16000
VAD_THRESHOLD = 0.5
PLAYBACK_PADDING_MS = 80

RESOURCES_DIR = str(RESOURCES_DIR)
VOSK_MODEL_PATH = os.path.join(RESOURCES_DIR, "vosk", "vosk-model-small-ru-0.22")
SOUND_DIR = os.path.join(RESOURCES_DIR, "sound", "jarvis-og", "ru")

SOUND_RUN = os.path.join(SOUND_DIR, "run.wav")
SOUND_OFF = os.path.join(SOUND_DIR, "off.wav")
SOUND_THANKS = os.path.join(SOUND_DIR, "thanks.wav")
SOUND_NOT_FOUND = os.path.join(SOUND_DIR, "not_found.wav")
SOUND_OK = [os.path.join(SOUND_DIR, f"ok{i}.wav") for i in range(1, 5)]
SOUND_REPLY = [os.path.join(SOUND_DIR, f"reply{i}.wav") for i in range(1, 4)]

warnings.filterwarnings("ignore", category=SyntaxWarning)

_vosk_model = None
_vad_model = None
_playback_lock = threading.Lock()


def get_vosk_model():
    global _vosk_model
    if _vosk_model is None:
        from vosk import Model
        print(f"Загружаю Vosk STT: {VOSK_MODEL_PATH}")
        if not os.path.isdir(VOSK_MODEL_PATH):
            raise FileNotFoundError(
                "Не найдена модель Vosk. "
                f"Ожидается: {VOSK_MODEL_PATH}"
            )
        _vosk_model = Model(VOSK_MODEL_PATH)
    return _vosk_model


def get_vad_model():
    global _vad_model
    if _vad_model is None:
        from silero_vad import load_silero_vad
        print("Загружаю Silero VAD...")
        _vad_model = load_silero_vad()
    return _vad_model


def _decode_pcm_to_float(frames: bytes, sample_width: int):
    if sample_width == 1:
        audio = np.frombuffer(frames, dtype=np.uint8)
        return (audio.astype(np.float32) - 128.0) / 128.0
    if sample_width == 2:
        audio = np.frombuffer(frames, dtype=np.int16)
        return audio.astype(np.float32) / 32768.0
    if sample_width == 3:
        raw = np.frombuffer(frames, dtype=np.uint8).reshape(-1, 3)
        values = (
            raw[:, 0].astype(np.int32)
            | (raw[:, 1].astype(np.int32) << 8)
            | (raw[:, 2].astype(np.int32) << 16)
        )
        values[values & 0x800000 != 0] -= 1 << 24
        return values.astype(np.float32) / 8388608.0
    if sample_width == 4:
        audio = np.frombuffer(frames, dtype=np.int32)
        return audio.astype(np.float32) / 2147483648.0
    raise ValueError(f"Неподдерживаемая разрядность WAV: {sample_width * 8} bit")


def play_sound(path: str) -> None:
    """Воспроизводит WAV целиком и не даёт другому потоку оборвать его."""
    if not path or not os.path.isfile(path):
        print(f"[Ошибка воспроизведения] Файл не найден: {path}")
        return

    try:
        with wave.open(path, "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            frame_rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())

        audio = _decode_pcm_to_float(frames, sample_width)
        if channels > 1:
            audio = audio.reshape(-1, channels)

        padding_frames = int(frame_rate * PLAYBACK_PADDING_MS / 1000)
        if channels > 1:
            padding = np.zeros((padding_frames, channels), dtype=np.float32)
        else:
            padding = np.zeros(padding_frames, dtype=np.float32)
        audio = np.concatenate((padding, audio, padding))

        with _playback_lock:
            sd.play(audio, samplerate=frame_rate)
            sd.wait()
    except Exception as e:
        print(f"[Ошибка воспроизведения] {e}")


def play_random_ok() -> None:
    if SOUND_OK:
        play_sound(random.choice(SOUND_OK))


def play_ack_sound() -> None:
    if SOUND_REPLY:
        play_sound(random.choice(SOUND_REPLY))


_WINDOW_SAMPLES = 512
_GRAMMAR_UNK = "[unk]"


def _build_grammar_json() -> str | None:
    try:
        from jarvis_commands import get_command_grammar_phrases
        phrases = get_command_grammar_phrases()
    except Exception as e:
        print(f"[Vosk grammar] Не удалось получить фразы команд: {e}")
        return None
    if not phrases:
        return None
    return json.dumps(sorted(set(phrases)) + [_GRAMMAR_UNK], ensure_ascii=False)


def record_and_transcribe(
    max_seconds: float = 12.0,
    silence_duration: float = 0.65,
    pre_speech_timeout: float = 5.0,
) -> dict:
    from vosk import KaldiRecognizer
    import torch
    from silero_vad import VADIterator

    recognizer = KaldiRecognizer(get_vosk_model(), SAMPLE_RATE)
    recognizer.SetWords(False)

    vad_iterator = VADIterator(
        get_vad_model(),
        threshold=VAD_THRESHOLD,
        sampling_rate=SAMPLE_RATE,
        min_silence_duration_ms=int(silence_duration * 1000),
        speech_pad_ms=120,
    )

    max_samples = int(max_seconds * SAMPLE_RATE)
    pre_speech_max_samples = int(pre_speech_timeout * SAMPLE_RATE)
    total_samples = 0
    speech_started = False
    pcm_chunks: list[bytes] = []

    print("Слушаю... (Vosk + Silero VAD)")

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32") as stream:
        while total_samples < max_samples:
            block, _ = stream.read(_WINDOW_SAMPLES)
            block = block.flatten()
            if len(block) < _WINDOW_SAMPLES:
                break

            total_samples += len(block)
            tensor = torch.from_numpy(block.copy())

            try:
                vad_event = vad_iterator(tensor, return_seconds=False)
            except TypeError:
                vad_event = vad_iterator(tensor)

            if vad_event and "start" in vad_event:
                speech_started = True

            pcm16 = np.clip(block * 32767.0, -32768, 32767).astype(np.int16)
            pcm_bytes = pcm16.tobytes()
            recognizer.AcceptWaveform(pcm_bytes)

            if speech_started:
                pcm_chunks.append(pcm_bytes)

            if not speech_started and total_samples >= pre_speech_max_samples:
                break
            if speech_started and vad_event and "end" in vad_event:
                break

    vad_iterator.reset_states()

    if not speech_started:
        return {"text": "", "grammar_text": None}

    try:
        result = json.loads(recognizer.FinalResult())
        text = (result.get("text") or "").strip()
    except Exception as e:
        print(f"[Vosk] Ошибка получения результата: {e}")
        text = ""

    print(f"[Vosk распознал]: {text}")

    grammar_text = None
    grammar_json = _build_grammar_json()
    if grammar_json and pcm_chunks:
        try:
            grammar_recognizer = KaldiRecognizer(
                get_vosk_model(), SAMPLE_RATE, grammar_json
            )
            for chunk in pcm_chunks:
                grammar_recognizer.AcceptWaveform(chunk)
            g_result = json.loads(grammar_recognizer.FinalResult())
            g_text = (g_result.get("text") or "").strip()
            if g_text and g_text != _GRAMMAR_UNK:
                grammar_text = g_text
            print(f"[Vosk grammar]: {g_text!r}")
        except Exception as e:
            print(f"[Vosk grammar] Ошибка: {e}")

    return {"text": text, "grammar_text": grammar_text}


def listen() -> dict:
    return record_and_transcribe()
