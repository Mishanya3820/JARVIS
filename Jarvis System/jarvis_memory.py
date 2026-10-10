from __future__ import annotations

import datetime as dt
import json
import os
import re
import threading
import uuid

from jarvis_paths import PROJECT_DIR

DATA_DIR = os.path.join(str(PROJECT_DIR), "data")
NOTES_FILE = os.path.join(DATA_DIR, "notes.json")
REMINDERS_FILE = os.path.join(DATA_DIR, "reminders.json")
_LOCK = threading.RLock()


def _load(path: str, default):
    with _LOCK:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError, TypeError):
            return default.copy() if isinstance(default, list) else dict(default)


def _save(path: str, value) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with _LOCK:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


def load_notes() -> list[dict]:
    return _load(NOTES_FILE, [])


def add_note(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("Текст заметки пустой.")
    notes = load_notes()
    note = {"id": uuid.uuid4().hex[:10], "text": text, "created_at": dt.datetime.now().isoformat(timespec="seconds")}
    notes.append(note)
    _save(NOTES_FILE, notes)
    return note


def delete_note(query: str) -> str:
    query = (query or "").strip()
    notes = load_notes()
    if not notes:
        return "Заметок пока нет."
    target = None
    if query.isdigit():
        index = int(query) - 1
        if 0 <= index < len(notes):
            target = notes[index]
    if target is None:
        q = query.lower()
        target = next((note for note in notes if q and q in note.get("text", "").lower()), None)
    if target is None:
        return "Такую заметку не нашёл."
    notes.remove(target)
    _save(NOTES_FILE, notes)
    return f"Заметка удалена: {target.get('text', '')}."


def delete_note_by_id(note_id: str) -> dict | None:
    """Удаляет заметку по её стабильному id (см. add_note). В отличие от
    delete_note(query) — точечное удаление без нечёткого поиска по тексту,
    для UI (кнопка "удалить" у конкретной заметки в списке)."""
    note_id = (note_id or "").strip()
    if not note_id:
        return None
    notes = load_notes()
    target = next((note for note in notes if note.get("id") == note_id), None)
    if target is None:
        return None
    notes.remove(target)
    _save(NOTES_FILE, notes)
    return target


def update_note(note_id: str, text: str) -> dict | None:
    """Меняет текст заметки по её id (кнопка "изменить" в списке заметок).
    Возвращает обновлённую заметку или None, если такой id нет. Пустой
    текст — ValueError, чтобы случайно не стереть заметку."""
    note_id = (note_id or "").strip()
    text = (text or "").strip()
    if not text:
        raise ValueError("Текст заметки пустой.")
    if not note_id:
        return None
    with _LOCK:
        notes = load_notes()
        target = next((note for note in notes if note.get("id") == note_id), None)
        if target is None:
            return None
        target["text"] = text
        target["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
        _save(NOTES_FILE, notes)
    return target


def format_notes() -> str:
    notes = load_notes()
    if not notes:
        return "Сейчас заметок нет."
    return "Сейчас ваши заметки: " + "; ".join(f"{i + 1}. {n.get('text', '')}" for i, n in enumerate(notes[-20:]))


# Числа, которые GigaAM может написать словами ("через двадцать минут",
# "в шесть вечера"). Нужны и парсеру времени ниже, и регулярке в jarvis_intent.
NUMBER_WORDS = {
    "ноль": 0, "один": 1, "одна": 1, "одну": 1, "два": 2, "две": 2, "три": 3,
    "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9,
    "десять": 10, "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13,
    "четырнадцать": 14, "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17,
    "восемнадцать": 18, "девятнадцать": 19, "двадцать": 20, "тридцать": 30,
    "сорок": 40, "пятьдесят": 50, "шестьдесят": 60,
}
_TENS_VALUES = {20, 30, 40, 50, 60}

_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
_TIME_HINT = "Не понял время напоминания. Пример: «через 20 минут», «в 18:30» или «завтра в 10:00»."
_CLOCK_RE = re.compile(
    r"(?:^|\s)(?:(?:в|на)\s+)?(\d{1,2})(?:[:.\s](\d{2}))?\s*(?:час(?:а|ов)?|ч)?(?:\s*(утра|вечера|дня|ночи))?\s*$"
)


def words_to_digits(text: str) -> str:
    """"через двадцать пять минут" -> "через 25 минут", "в шесть тридцать
    вечера" -> "в 6 30 вечера", "через полчаса" -> "через 30 минут".
    Применяется только к фразе со временем, а не к тексту напоминания."""
    text = (text or "").lower().replace("ё", "е")
    text = re.sub(r"\bполчаса\b", "30 минут", text)
    text = re.sub(r"\bполтора\s+часа\b", "90 минут", text)
    text = re.sub(r"\bчерез\s+(час|минуту|секунду)\b", r"через 1 \1", text)
    tokens = text.split()
    out: list[str] = []
    i = 0
    while i < len(tokens):
        value = NUMBER_WORDS.get(tokens[i])
        if value is None:
            out.append(tokens[i])
            i += 1
            continue
        if value in _TENS_VALUES and i + 1 < len(tokens) and 1 <= NUMBER_WORDS.get(tokens[i + 1], 0) <= 9:
            value += NUMBER_WORDS[tokens[i + 1]]
            i += 1
        out.append(str(value))
        i += 1
    return " ".join(out)


def _apply_part_of_day(hour: int, part: str | None) -> int:
    if part == "вечера" and hour < 12:
        return hour + 12
    if part == "дня" and 1 <= hour <= 6:
        return hour + 12
    if part == "ночи":
        if hour == 12:
            return 0
        if 9 <= hour < 12:
            return hour + 12
    return hour


def _clock_from(text: str) -> tuple[int, int] | None:
    match = _CLOCK_RE.search((text or "").strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    hour = _apply_part_of_day(hour, match.group(3))
    return (hour, minute) if 0 <= hour <= 23 and 0 <= minute <= 59 else None


def parse_reminder_datetime(spec: str, now: dt.datetime | None = None) -> dt.datetime:
    now = now or dt.datetime.now()
    raw = re.sub(r"\s+", " ", (spec or "").strip().lower().replace("ё", "е")).strip(" .,!?;:")
    raw = re.sub(r"^на\s+", "", words_to_digits(raw))

    relative = re.fullmatch(r"через\s+(\d+)\s*(секунд\w*|сек|минут\w*|мин|час\w*|ч|дн\w*|день)", raw)
    if relative:
        amount, unit = int(relative.group(1)), relative.group(2)
        if unit.startswith("сек"):
            return now + dt.timedelta(seconds=amount)
        if unit.startswith("мин"):
            return now + dt.timedelta(minutes=amount)
        if unit.startswith("ч"):
            return now + dt.timedelta(hours=amount)
        return now + dt.timedelta(days=amount)

    # Дата с названием месяца разбирается ДО простого времени: раньше
    # "5 октября в 14:00" ловилось как просто "в 14:00" и дата терялась.
    date_match = re.search(r"(\d{1,2})\s+(" + "|".join(_MONTHS) + r")(?:\s+(\d{4}))?", raw)
    if date_match:
        day, month = int(date_match.group(1)), _MONTHS[date_match.group(2)]
        year = int(date_match.group(3) or now.year)
        hour, minute = _clock_from(raw[date_match.end():]) or (9, 0)
        try:
            result = dt.datetime(year, month, day, hour, minute)
        except ValueError:
            raise ValueError("Не понял дату напоминания.") from None
        if result <= now and not date_match.group(3):
            result = result.replace(year=year + 1)
        return result

    day_offset = None
    for word, offset in (("послезавтра", 2), ("завтра", 1), ("сегодня", 0)):
        if raw.startswith(word):
            day_offset = offset
            raw = raw[len(word):].strip()
            break
    if day_offset is not None and not raw:
        if day_offset == 0:
            raise ValueError(_TIME_HINT)
        return (now + dt.timedelta(days=day_offset)).replace(hour=9, minute=0, second=0, microsecond=0)

    clock = _clock_from(raw)
    if clock:
        hour, minute = clock
        result = (now + dt.timedelta(days=day_offset or 0)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if result <= now:
            if day_offset is not None:
                raise ValueError("Это время уже прошло. Назовите время в будущем.")
            result += dt.timedelta(days=1)
        return result

    raise ValueError(_TIME_HINT)


def add_reminder(text: str, when: str) -> dict:
    text, when = (text or "").strip(), (when or "").strip()
    if not text:
        raise ValueError("Текст напоминания пустой.")
    due = parse_reminder_datetime(when)
    reminders = _load(REMINDERS_FILE, [])
    reminder = {"id": uuid.uuid4().hex[:10], "text": text, "when": when, "due_at": due.isoformat(timespec="seconds"), "done": False, "created_at": dt.datetime.now().isoformat(timespec="seconds")}
    reminders.append(reminder)
    reminders.sort(key=lambda item: item.get("due_at", ""))
    _save(REMINDERS_FILE, reminders)
    return reminder


def load_reminders(include_done: bool = False) -> list[dict]:
    reminders = _load(REMINDERS_FILE, [])
    return reminders if include_done else [item for item in reminders if not item.get("done")]


def format_reminders() -> str:
    reminders = load_reminders()
    if not reminders:
        return "Сейчас активных напоминаний нет."
    parts = []
    for i, reminder in enumerate(reminders[:20], 1):
        try:
            stamp = dt.datetime.fromisoformat(reminder["due_at"]).strftime("%d.%m в %H:%M")
        except Exception:
            stamp = reminder.get("when", "")
        parts.append(f"{i}. {stamp} — {reminder.get('text', '')}")
    return "Сейчас ваши напоминания: " + "; ".join(parts)


def start_reminder_scheduler(callback=None, interval: float = 1.0) -> threading.Event:
    stop_event = threading.Event()

    def worker():
        while not stop_event.wait(interval):
            reminders = load_reminders(include_done=True)
            now = dt.datetime.now()
            changed = False
            for reminder in reminders:
                if reminder.get("done"):
                    continue
                try:
                    due = dt.datetime.fromisoformat(reminder["due_at"])
                except (KeyError, TypeError, ValueError):
                    continue
                if due <= now:
                    reminder["done"] = True
                    reminder["triggered_at"] = now.isoformat(timespec="seconds")
                    changed = True
                    if callback:
                        try:
                            callback(reminder)
                        except Exception as exc:
                            print(f"[Reminders] Ошибка callback: {exc}")
            if changed:
                _save(REMINDERS_FILE, reminders)

    threading.Thread(target=worker, daemon=True, name="JARVIS-Reminders").start()
    return stop_event
