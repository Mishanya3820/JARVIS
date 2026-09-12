import os
import random
import threading
import warnings
import wave

import numpy as np
import sounddevice as sd

from jarvis_paths import RESOURCES_DIR


# ============================================================
# НАСТРОЙКИ
# ============================================================

SAMPLE_RATE = 16000

VAD_THRESHOLD = 0.5

# После этой продолжительности тишины считаем фразу законченной
SILENCE_DURATION = 0.30

# Размер блока микрофона
_WINDOW_SAMPLES = 512

# Задержка вокруг воспроизведения звука
PLAYBACK_PADDING_MS = 80


# ============================================================
# GIGAAM
# ============================================================

GIGAAM_DIR = os.path.join(
    str(RESOURCES_DIR),
    "gigaam_v3"
)

GIGAAM_ENCODER = os.path.join(
    GIGAAM_DIR,
    "gigaam_v3_e2e_rnnt_encoder_int8.onnx"
)

GIGAAM_DECODER = os.path.join(
    GIGAAM_DIR,
    "decoder.onnx"
)

GIGAAM_JOINER = os.path.join(
    GIGAAM_DIR,
    "joiner.onnx"
)

GIGAAM_TOKENS = os.path.join(
    GIGAAM_DIR,
    "tokens.txt"
)

# Для GT 1030 / обычного CPU
GIGAAM_NUM_THREADS = 2


# ============================================================
# ЗВУКИ JARVIS
# ============================================================

SOUND_DIR = os.path.join(
    str(RESOURCES_DIR),
    "sound",
    "jarvis-og",
    "ru"
)

SOUND_RUN = os.path.join(
    SOUND_DIR,
    "run.wav"
)

SOUND_OFF = os.path.join(
    SOUND_DIR,
    "off.wav"
)

SOUND_THANKS = os.path.join(
    SOUND_DIR,
    "thanks.wav"
)

SOUND_NOT_FOUND = os.path.join(
    SOUND_DIR,
    "not_found.wav"
)

SOUND_OK = [
    os.path.join(SOUND_DIR, f"ok{i}.wav")
    for i in range(1, 5)
]

SOUND_REPLY = [
    os.path.join(SOUND_DIR, f"reply{i}.wav")
    for i in range(1, 4)
]


# ============================================================
# ГЛОБАЛЬНЫЕ ОБЪЕКТЫ
# ============================================================

_gigaam_model = None
_vad_model = None

_playback_lock = threading.Lock()

warnings.filterwarnings(
    "ignore",
    category=SyntaxWarning
)


# ============================================================
# GIGAAM MODEL
# ============================================================

def get_gigaam_model():
    """
    Загружает GigaAM v3 один раз и оставляет модель в памяти.
    """

    global _gigaam_model

    if _gigaam_model is not None:
        return _gigaam_model

    import sherpa_onnx

    required_files = [
        GIGAAM_ENCODER,
        GIGAAM_DECODER,
        GIGAAM_JOINER,
        GIGAAM_TOKENS,
    ]

    for path in required_files:
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"GigaAM: не найден файл модели:\n{path}"
            )

    print("[GigaAM] Загружаю модель...")

    _gigaam_model = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=GIGAAM_ENCODER,
        decoder=GIGAAM_DECODER,
        joiner=GIGAAM_JOINER,
        tokens=GIGAAM_TOKENS,
        num_threads=GIGAAM_NUM_THREADS,
        sample_rate=SAMPLE_RATE,
        feature_dim=64,
        decoding_method="greedy_search",
        model_type="nemo_transducer",
    )

    print("[GigaAM] Модель загружена.")

    return _gigaam_model


# ============================================================
# SILERO VAD
# ============================================================

def get_vad_model():
    """
    Загружает Silero VAD один раз.
    """

    global _vad_model

    if _vad_model is not None:
        return _vad_model

    from silero_vad import load_silero_vad

    print("[VAD] Загружаю Silero VAD...")

    _vad_model = load_silero_vad()

    print("[VAD] Silero VAD загружен.")

    return _vad_model


# ============================================================
# WAV PLAYBACK
# ============================================================

def _decode_pcm_to_float(
    frames: bytes,
    sample_width: int
):
    if sample_width == 1:
        audio = np.frombuffer(
            frames,
            dtype=np.uint8
        )

        return (
            audio.astype(np.float32) - 128.0
        ) / 128.0

    if sample_width == 2:
        audio = np.frombuffer(
            frames,
            dtype=np.int16
        )

        return audio.astype(
            np.float32
        ) / 32768.0

    if sample_width == 3:
        raw = np.frombuffer(
            frames,
            dtype=np.uint8
        ).reshape(-1, 3)

        values = (
            raw[:, 0].astype(np.int32)
            | (raw[:, 1].astype(np.int32) << 8)
            | (raw[:, 2].astype(np.int32) << 16)
        )

        values[
            values & 0x800000 != 0
        ] -= 1 << 24

        return values.astype(
            np.float32
        ) / 8388608.0

    if sample_width == 4:
        audio = np.frombuffer(
            frames,
            dtype=np.int32
        )

        return audio.astype(
            np.float32
        ) / 2147483648.0

    raise ValueError(
        f"Неподдерживаемая разрядность WAV: "
        f"{sample_width * 8} bit"
    )


def play_sound(path: str) -> None:
    """
    Воспроизводит WAV-файл полностью.
    """

    if not path or not os.path.isfile(path):
        print(
            f"[Ошибка воспроизведения] "
            f"Файл не найден: {path}"
        )
        return

    try:
        with wave.open(path, "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            frame_rate = wf.getframerate()
            frames = wf.readframes(
                wf.getnframes()
            )

        audio = _decode_pcm_to_float(
            frames,
            sample_width
        )

        if channels > 1:
            audio = audio.reshape(
                -1,
                channels
            )

        padding_frames = int(
            frame_rate
            * PLAYBACK_PADDING_MS
            / 1000
        )

        if channels > 1:
            padding = np.zeros(
                (
                    padding_frames,
                    channels
                ),
                dtype=np.float32
            )
        else:
            padding = np.zeros(
                padding_frames,
                dtype=np.float32
            )

        audio = np.concatenate(
            (
                padding,
                audio,
                padding
            )
        )

        with _playback_lock:
            sd.play(
                audio,
                samplerate=frame_rate
            )

            sd.wait()

    except Exception as e:
        print(
            f"[Ошибка воспроизведения] {e}"
        )


def play_random_ok() -> None:
    """
    Проигрывает случайный звук успешного выполнения.
    """

    available = [
        path
        for path in SOUND_OK
        if os.path.isfile(path)
    ]

    if available:
        play_sound(
            random.choice(available)
        )


def play_ack_sound() -> None:
    """
    Проигрывает случайный звук подтверждения.
    """

    available = [
        path
        for path in SOUND_REPLY
        if os.path.isfile(path)
    ]

    if available:
        play_sound(
            random.choice(available)
        )


# ============================================================
# GIGAAM TRANSCRIPTION
# ============================================================

def transcribe_gigaam(
    audio: np.ndarray
) -> str:
    """
    Распознаёт готовый float32-массив через GigaAM.
    """

    recognizer = get_gigaam_model()

    audio = np.asarray(
        audio,
        dtype=np.float32
    ).reshape(-1)

    if audio.size == 0:
        return ""

    stream = recognizer.create_stream()

    stream.accept_waveform(
        SAMPLE_RATE,
        audio
    )

    recognizer.decode_stream(
        stream
    )

    return stream.result.text.strip()


# ============================================================
# RECORD + TRANSCRIBE
# ============================================================

def record_and_transcribe(
    max_seconds: float = 12.0,
    silence_duration: float = SILENCE_DURATION,
    pre_speech_timeout: float = 5.0,
) -> dict:
    """
    Слушает микрофон через Silero VAD,
    затем передаёт готовую фразу в GigaAM.

    Возвращает тот же формат,
    который ожидает текущий jarvis_gui.py:

        {
            "text": "...",
            "grammar_text": None
        }
    """

    import torch
    from silero_vad import VADIterator

    vad = get_vad_model()

    vad_iterator = VADIterator(
        vad,
        threshold=VAD_THRESHOLD,
        sampling_rate=SAMPLE_RATE,
        min_silence_duration_ms=int(
            silence_duration * 1000
        ),
        speech_pad_ms=100,
    )

    max_samples = int(
        max_seconds * SAMPLE_RATE
    )

    pre_speech_max_samples = int(
        pre_speech_timeout * SAMPLE_RATE
    )

    total_samples = 0

    speech_started = False

    audio_chunks = []

    print(
        "Слушаю... (GigaAM + Silero VAD)"
    )

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=_WINDOW_SAMPLES,
        ) as stream:

            while total_samples < max_samples:

                block, overflowed = stream.read(
                    _WINDOW_SAMPLES
                )

                block = block.flatten()

                if len(block) < _WINDOW_SAMPLES:
                    break

                total_samples += len(block)

                tensor = torch.from_numpy(
                    block.copy()
                )

                try:
                    vad_event = vad_iterator(
                        tensor,
                        return_seconds=False
                    )
                except TypeError:
                    vad_event = vad_iterator(
                        tensor
                    )

                # --------------------------------------------
                # Начало речи
                # --------------------------------------------

                if (
                    vad_event
                    and "start" in vad_event
                ):
                    speech_started = True

                    print(
                        "[VAD] Речь обнаружена."
                    )

                # --------------------------------------------
                # Сохраняем аудио только после начала речи
                # --------------------------------------------

                if speech_started:
                    audio_chunks.append(
                        block.copy()
                    )

                # --------------------------------------------
                # Никто не начал говорить
                # --------------------------------------------

                if (
                    not speech_started
                    and total_samples
                    >= pre_speech_max_samples
                ):
                    print(
                        "[VAD] Таймаут ожидания речи."
                    )
                    break

                # --------------------------------------------
                # Конец речи
                # --------------------------------------------

                if (
                    speech_started
                    and vad_event
                    and "end" in vad_event
                ):
                    print(
                        "[VAD] Конец речи."
                    )
                    break

    finally:
        try:
            vad_iterator.reset_states()
        except Exception:
            pass

    # --------------------------------------------------------
    # Речи нет
    # --------------------------------------------------------

    if not speech_started or not audio_chunks:
        return {
            "text": "",
            "grammar_text": None,
        }

    # --------------------------------------------------------
    # Объединяем аудио
    # --------------------------------------------------------

    audio = np.concatenate(
        audio_chunks
    ).astype(np.float32)

    if len(audio) > max_samples:
        audio = audio[:max_samples]

    # --------------------------------------------------------
    # GigaAM
    # --------------------------------------------------------

    print(
        f"[GigaAM] Распознавание "
        f"({len(audio) / SAMPLE_RATE:.2f} сек)..."
    )

    try:
        text = transcribe_gigaam(
            audio
        )

    except Exception as e:
        print(
            f"[GigaAM] Ошибка распознавания: {e}"
        )

        return {
            "text": "",
            "grammar_text": None,
        }

    print(
        f"[GigaAM распознал]: {text}"
    )

    return {
        "text": text,
        "grammar_text": None,
    }


# ============================================================
# PUBLIC API
# ============================================================

def listen() -> dict:
    return record_and_transcribe()


def warmup_voice_models():
    """
    Предварительно загружает GigaAM и Silero VAD.
    """

    print(
        "[Voice] Предзагрузка голосовых моделей..."
    )

    get_vad_model()
    get_gigaam_model()

    print(
        "[Voice] Голосовые модели готовы."
    )