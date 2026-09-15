from __future__ import annotations

import datetime as dt
import json
import os
import re
import threading
import time
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
                value = json.load(f)
            return value
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
    note = {
        "id": uuid.uuid4().hex[:10],
        "text": text,
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
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
        for note in notes:
            if q and q in note.get("text", "").lower():
                target = note
                break
    if target is None:
        return "Такую заметку не нашёл."
    notes.remove(target)
    _save(NOTES_FILE, notes)
    return f"Заметка удалена: {target.get('text', '')}."


def format_notes() -> str:
    notes = load_notes()
    if not notes:
        return "Сейчас заметок нет."
    parts = [f"{i + 1}. {note.get('text', '')}" for i, note in enumerate(notes[-20:])]
    return "Сейчас ваши заметки: " + "; ".join(parts)


def _parse_clock(value: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"(\d{1,2})(?::|\.)?(\d{2})?", value.strip())
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def parse_reminder_datetime(spec: str, now: dt.datetime | None = None) -> dt.datetime:
    now = now or dt.datetime.now()
    raw = (spec or "").strip().lower().replace("ё", "е")
    raw = re.sub(r"\s+", " ", raw)

    relative = re.fullmatch(r"через\s+(\d+)\s*(минут(?:у|ы)?|мин|час(?:а|ов)?|ч)", raw)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2)
        delta = dt.timedelta(hours=amount) if unit.startswith(("час", "ч")) else dt.timedelta(minutes=amount)
        return now + delta

    tomorrow = raw.startswith("завтра")
    if tomorrow:
        raw = raw[len("завтра"):].strip()

    clock_match = re.search(r"(?:в\s*)?(\d{1,2}(?::|\.)\d{2}|\d{1,2})\s*(?:час(?:а|ов)?|ч)?$", raw)
    if clock_match:
        clock = _parse_clock(clock_match.group(1))
        if clock:
            hour, minute = clock
            base = now + dt.timedelta(days=1) if tomorrow else now
            result = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if not tomorrow and result <= now:
                result += dt.timedelta(days=1)
            return result

    months = {
        "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
        "мая": 5, "июня": 6, "июля": 7, "августа": 8,
        "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
    }
    date_match = re.search(r"(\d{1,2})\s+([а-я]+)(?:\s+(\d{4}))?", raw)
    if date_match and date_match.group(2) in months:
        day = int(date_match.group(1))
        month = months[date_match.group(2)]
        year = int(date_match.group(3) or now.year)
        tail = raw[date_match.end():].strip()
        clock_match = re.search(r"(?:в\s*)?(\d{1,2})(?::|\.)(\d{2})", tail)
        hour, minute = (int(clock_match.group(1)), int(clock_match.group(2))) if clock_match else (9, 0)
        result = dt.datetime(year, month, day, hour, minute)
        if result <= now and not date_match.group(3):
            result = result.replace(year=year + 1)
        return result

    raise ValueError("Не понял время напоминания. Пример: «через 20 минут», «в 18:30» или «завтра в 10:00».")


def add_reminder(text: str, when: str) -> dict:
    text = (text or "").strip()
    when = (when or "").strip()
    if not text:
        raise ValueError("Текст напоминания пустой.")
    due = parse_reminder_datetime(when)
    reminders = _load(REMINDERS_FILE, [])
    reminder = {
        "id": uuid.uuid4().hex[:10],
        "text": text,
        "when": when,
        "due_at": due.isoformat(timespec="seconds"),
        "done": False,
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    reminders.append(reminder)
    reminders.sort(key=lambda item: item.get("due_at", ""))
    _save(REMINDERS_FILE, reminders)
    return reminder


def load_reminders(include_done: bool = False) -> list[dict]:
    reminders = _load(REMINDERS_FILE, [])
    if include_done:
        return reminders
    return [item for item in reminders if not item.get("done")]


def delete_reminder(query: str) -> str:
    query = (query or "").strip()
    reminders = load_reminders(include_done=True)
    active = [r for r in reminders if not r.get("done")]
    if not active:
        return "Активных напоминаний нет."
    target = None
    if query.isdigit():
        index = int(query) - 1
        if 0 <= index < len(active):
            target = active[index]
    if target is None:
        q = query.lower()
        for reminder in active:
            if q and q in reminder.get("text", "").lower():
                target = reminder
                break
    if target is None:
        return "Такое напоминание не нашёл."
    reminders.remove(target)
    _save(REMINDERS_FILE, reminders)
    return f"Напоминание отменено: {target.get('text', '')}."


def format_reminders() -> str:
    reminders = load_reminders()
    if not reminders:
        return "Сейчас активных напоминаний нет."
    parts = []
    for i, reminder in enumerate(reminders[:20], 1):
        try:
            due = dt.datetime.fromisoformat(reminder["due_at"])
            stamp = due.strftime("%d.%m в %H:%M")
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
