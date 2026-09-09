"""Лёгкий локальный классификатор намерений JARVIS."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any


@dataclass
class IntentResult:
    intent_id: str
    confidence: float
    slots: dict[str, Any] = field(default_factory=dict)


def normalize_text(text: str) -> str:
    text = (text or "").lower().replace("ё", "е")
    text = re.sub(r"[^a-zа-я0-9.:/_\\ -]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _score(text: str, phrase: str, command: dict | None = None) -> float:
    """Сравнивает фразу и учитывает естественные добавления аргументов."""
    a = normalize_text(text)
    b = normalize_text(phrase)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    # Для slot-команд начало фразы является главным признаком намерения.
    if a.startswith(b + " "):
        return 0.95

    # "открой github.com" / "зайди на youtube.com" — сильный признак
    # открытия URL, даже если в command.json написано "открой сайт".
    has_url = bool(re.search(r"(?:https?://|www\.|[a-z0-9-]+\.[a-z]{2,})(?:/\S*)?", a, re.I))
    if command and "url" in command.get("slots", []) and has_url:
        if a.startswith(("открой ", "зайди на ", "перейди на ", "открой сайт ", "зайди на сайт ")):
            return 0.93

    seq = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    overlap = len(ta & tb) / max(len(tb), 1)
    return seq * 0.6 + overlap * 0.4


def _extract_query(raw: str) -> str | None:
    patterns = (
        r"(?:найди|поищи|загугли)\s+(?:в\s+интернете\s+)?(.+)$",
        r"поиск(?:ать)?\s+(?:в\s+интернете\s+)?(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, raw, re.I)
        if match:
            value = match.group(1).strip()
            if value:
                return value
    return None


def _extract_url(raw: str) -> str | None:
    match = re.search(
        r"(?:открой(?:\s+сайт)?|зайди(?:\s+на)?(?:\s+сайт)?|перейди(?:\s+на)?(?:\s+сайт)?)\s+"
        r"(https?://\S+|www\.\S+|[a-z0-9а-я-]+\.[a-z]{2,}(?:/\S*)?)",
        raw,
        re.I,
    )
    if not match:
        return None
    return match.group(1).strip().rstrip(".,!?;:)")


def _extract_path(raw: str) -> str | None:
    # Windows path: D:\Games\... или C:/Users/...
    match = re.search(r"(?:открой|запусти|перейди\s+в)\s+([a-zA-Z]:[\\/][^\n]+)$", raw, re.I)
    if match:
        return match.group(1).strip().rstrip(".,")

    match = re.search(r"(?:открой|запусти|перейди\s+в)\s+(.+)$", raw, re.I)
    if match:
        return match.group(1).strip().rstrip(".,")
    return None


def extract_slots(text: str, slot_names: list[str]) -> dict[str, str]:
    raw = (text or "").strip()
    result: dict[str, str] = {}

    if "query" in slot_names:
        query = _extract_query(raw)
        if query:
            result["query"] = query

    if "url" in slot_names:
        url = _extract_url(raw)
        if url:
            result["url"] = url

    if "path" in slot_names:
        path = _extract_path(raw)
        if path:
            result["path"] = path

    return result


def classify(text: str, commands: list[dict]) -> IntentResult | None:
    normalized = normalize_text(text)
    if not normalized:
        return None

    best: tuple[float, dict] | None = None
    for command in commands:
        for phrase in command.get("phrases", []):
            score = _score(normalized, phrase, command)
            if best is None or score > best[0]:
                best = (score, command)

    if best is None:
        return None

    score, command = best
    threshold = float(command.get("threshold", 0.72))
    if score < threshold:
        return None

    slot_names = list(command.get("slots", []))
    return IntentResult(
        intent_id=command["id"],
        confidence=score,
        slots=extract_slots(text, slot_names),
    )
