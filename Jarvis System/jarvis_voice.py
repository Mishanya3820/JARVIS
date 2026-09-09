import json
import os
import random
import warnings
import wave
 
import numpy as np
import sounddevice as sd
import torch
from silero_vad import load_silero_vad, VADIterator
from vosk import Model, KaldiRecognizer
 
 
SAMPLE_RATE = 16000
VAD_THRESHOLD = 0.5
 
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
RESOURCES_DIR = os.path.join(PROJECT_DIR, "resources", "sound", "jarvis-og", "ru")
VOSK_MODEL_PATH = os.path.join(PROJECT_DIR, "resources", "vosk", "vosk-model-small-ru-0.22")
 
SOUND_RUN = os.path.join(RESOURCES_DIR, "run.wav")
SOUND_OFF = os.path.join(RESOURCES_DIR, "off.wav")
SOUND_THANKS = os.path.join(RESOURCES_DIR, "thanks.wav")
SOUND_NOT_FOUND = os.path.join(RESOURCES_DIR, "not_found.wav")
SOUND_OK = [os.path.join(RESOURCES_DIR, f"ok{i}.wav") for i in range(1, 5)]
SOUND_REPLY = [os.path.join(RESOURCES_DIR, f"reply{i}.wav") for i in range(1, 4)]
 
warnings.filterwarnings("ignore", category=SyntaxWarning)
 
_vosk_model = None
_vad_model = None
 
 
def get_vosk_model():
    """Лениво загружает Vosk STT с диска проекта."""
    global _vosk_model
    if _vosk_model is None:
        print(f"Загружаю Vosk STT: {VOSK_MODEL_PATH}")
        if not os.path.isdir(VOSK_MODEL_PATH):
            raise FileNotFoundError(
                "Не найдена модель Vosk. "
                f"Ожидается: {VOSK_MODEL_PATH}"
            )
        _vosk_model = Model(VOSK_MODEL_PATH)
    return _vosk_model
 
 
def get_vad_model():
    """Лениво загружает Silero VAD.
 
    Это НЕ TTS. VAD только определяет, когда человек начал/закончил говорить.
    """
    global _vad_model
    if _vad_model is None:
        print("Загружаю Silero VAD...")
        _vad_model = load_silero_vad()
    return _vad_model
 
 
def play_sound(path: str) -> None:
    if not path or not os.path.isfile(path):
        print(f"[Ошибка воспроизведения] Файл не найден: {path}")
        return
 
    try:
        with wave.open(path, "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            frame_rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
 
        dtype = {1: np.uint8, 2: np.int16, 4: np.int32}.get(sample_width, np.int16)
        audio = np.frombuffer(frames, dtype=dtype)
 
        if channels > 1:
            audio = audio.reshape(-1, channels)
 
        if dtype == np.uint8:
            audio_float = (audio.astype(np.float32) - 128.0) / 128.0
        else:
            audio_float = audio.astype(np.float32) / float(np.iinfo(dtype).max)
 
        sd.play(audio_float, samplerate=frame_rate)
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
    """Строит JSON-грамматику Vosk из фраз всех команд (jarvis_commands).
 
    Грамматически-ограниченное распознавание — тот же приём, что у
    Priler в Rust-версии для WAKE_RECOGNIZER (Recognizer::new_with_grammar),
    только здесь применяется и к обычным командам. Смысл: когда декодер
    Kaldi не пытается выбрать из ВСЕГО словаря языковой модели, а лишь
    из небольшого заданного набора фраз, слова вроде "дискорд" или
    "стим" распознаются намного надёжнее — им не приходится
    конкурировать с более "вероятными" словами полной языковой модели.
 
    Важная оговорка: если конкретного слова вообще нет в словаре модели
    (в её лексиконе/FST), грамматика тоже не поможет — она может выбрать
    только из слов, которые модель в принципе знает. Если после этой
    правки Vosk в грамматическом режиме всё равно не может распознать
    что-то конкретное — смотри комментарий в jarvis_commands/README.
    """
    try:
        from jarvis_commands import get_command_grammar_phrases
 
        phrases = get_command_grammar_phrases()
    except Exception as e:
        print(f"[Vosk grammar] Не удалось получить фразы команд: {e}")
        return None
 
    if not phrases:
        return None
 
    # [unk] — обязательный "мусорный" токен: если сказанное не похоже ни
    # на одну фразу из списка, распознаватель вернёт его вместо того,
    # чтобы силой притягивать чужую речь к ближайшей известной фразе.
    return json.dumps(sorted(set(phrases)) + [_GRAMMAR_UNK], ensure_ascii=False)
 
 
def record_and_transcribe(
    max_seconds: float = 12.0,
    silence_duration: float = 0.65,
    pre_speech_timeout: float = 5.0,
) -> dict:
    """Vosk STT + Silero VAD в потоковом режиме.
 
    Возвращает {"text": свободный текст, "grammar_text": текст из
    грамматически-ограниченного прохода или None}.
 
    Свободный проход идёт в реальном времени (нужен и для обычных
    вопросов к Groq, где грамматика неприменима). Грамматический
    проход выполняется один раз, сразу после окончания записи, над уже
    накопленным аудио — это не проход в реальном времени, а быстрый
    повторный разбор буфера (Vosk decoding кратно быстрее реального
    времени, так что задержка от этого практически не ощущается).
    """
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
 
            # Копим сырые сэмплы только с момента начала речи — второй
            # (грамматический) проход не нуждается в тишине "до" фразы.
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
            grammar_recognizer = KaldiRecognizer(get_vosk_model(), SAMPLE_RATE, grammar_json)
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
