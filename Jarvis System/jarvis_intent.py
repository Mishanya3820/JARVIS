from __future__ import annotations
 
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any
 
from rapidfuzz.distance import Levenshtein
 
 
@dataclass
class IntentResult:
    intent_id: str
    confidence: float
    slots: dict[str, Any] = field(default_factory=dict)
 
 
def normalize_text(text: str) -> str:
    text = (text or "").lower().replace("ё", "е")
    text = re.sub(r"[^a-zа-я0-9.:/_\\ -]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()
 
 
def _subsequence_reduce(a_words: list[str], b_words: list[str]) -> str | None:
    """Если все слова фразы команды (b) встречаются среди слов пользователя
    (a) в ТОМ ЖЕ порядке, но вперемешку с лишними словами — например
    "сделай МНЕ напоминание" вместо "сделай напоминание" — возвращает a
    без этих лишних слов. Порядок и сами слова должны совпасть буквально
    (без нечёткости), поэтому антонимы вроде "открой"/"закрой" здесь
    никогда не перепутаются между собой."""
    i = 0
    kept: list[str] = []
    for word in a_words:
        if i < len(b_words) and word == b_words[i]:
            kept.append(word)
            i += 1
    return " ".join(kept) if i == len(b_words) else None
 
 
def _score(text: str, phrase: str, command: dict | None = None) -> float:
    a = normalize_text(text)
    b = normalize_text(phrase)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a.startswith(b + " "):
        return 0.95
    has_url = bool(re.search(r"(?:https?://|www\.|[a-z0-9-]+\.[a-z]{2,})(?:/\S*)?", a, re.I))
    if command and "url" in command.get("slots", []) and has_url:
        if a.startswith(("открой ", "зайди на ", "перейди на ", "открой сайт ", "зайди на сайт ")):
            return 0.93
    # Схожесть по символам — честное совмещение расстояния Левенштейна
    # (rapidfuzz) и SequenceMatcher: они по-разному штрафуют перестановки
    # и лишние буквы, среднее устойчивее любого из них по отдельности.
    lev = Levenshtein.normalized_similarity(a, b)
    seq = SequenceMatcher(None, a, b).ratio()
    char_sim = (lev + seq) / 2
    # Пересечение слов — основная защита от путаницы противоположных команд
    # ("открой"/"закрой", "включи"/"выключи"): если ключевое слово фразы
    # не встретилось в тексте вообще, оценка ощутимо падает даже при
    # высокой посимвольной схожести.
    ta, tb = set(a.split()), set(b.split())
    overlap = len(ta & tb) / max(len(tb), 1)
    combined = char_sim * 0.6 + overlap * 0.4
    # Отдельно: лишние слова внутри фразы не должны мешать распознаванию
    # ("сделай МНЕ напоминание ..."). Даём этому пути высокую, но не
    # максимальную уверенность (ниже точного/префиксного совпадения) —
    # иначе он может перебить настоящее точное совпадение другой, более
    # короткой команды, чьи слова случайно оказались подпоследовательностью.
    reduced = _subsequence_reduce(a.split(), b.split())
    reduced_score = 0.94 if reduced is not None else 0.0
    return max(combined, reduced_score)
 
 
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
        r"(?:открой(?:\s+сайт|\s+ссылку)?|зайди(?:\s+на)?(?:\s+сайт)?|перейди(?:\s+на(?:\s+сайт)?|\s+по\s+ссылке))\s+"
        r"(https?://\S+|www\.\S+|[a-z0-9а-я-]+\.[a-z]{2,}(?:/\S*)?)",
        raw,
        re.I,
    )
    if not match:
        return None
    return match.group(1).strip().rstrip(".,!?;:)")
 
 
def _extract_path(raw: str) -> str | None:
    match = re.search(r"(?:открой|запусти|перейди\s+в)\s+([a-zA-Z]:[\\/][^\n]+)$", raw, re.I)
    if match:
        return match.group(1).strip().rstrip(".,")
    match = re.search(r"(?:открой|запусти|перейди\s+в)\s+(.+)$", raw, re.I)
    if match:
        return match.group(1).strip().rstrip(".,")
    return None
 
 
def _extract_after_prefix(raw: str, prefixes: tuple[str, ...]) -> str | None:
    lowered = raw.lower().replace("ё", "е")
    for prefix in prefixes:
        match = re.match(r"^\s*" + re.escape(prefix) + r"\s+(.+?)\s*$", lowered, re.I)
        if match:
            return raw[match.start(1):match.end(1)].strip().rstrip(".,!?;:")
    return None
 
 
_REMINDER_WHEN = (
    r"(?:через\s+(?:\d+\s*)?(?:минут(?:у|ы)?|мин|час(?:а|ов)?|ч)"
    r"|завтра(?:\s+в\s+\d{1,2}(?::|\.)\d{2})?"
    r"|в\s+\d{1,2}(?::|\.)\d{2}"
    r"|\d{1,2}\s+[а-я]+(?:\s+\d{4})?(?:\s+в\s+\d{1,2}(?::|\.)\d{2})?)"
)
_REMINDER_VERB = r"^(?:напомни(?:\s+мне)?|(?:поставь|создай|сделай)(?:\s+мне)?\s+напоминание)\s+"
 
 
def _extract_reminder(raw: str) -> tuple[str | None, str | None]:
    text = (raw or "").strip()
    verb_match = re.match(_REMINDER_VERB, text, re.I)
    if not verb_match:
        return None, None
    rest = text[verb_match.end():]
    # Время может стоять и до, и после текста напоминания — "напомни мне
    # ПОЗВОНИТЬ МАМЕ через 20 минут" так же естественно, как и "напомни
    # через 20 минут позвонить маме". Ищем "when" в любом месте остатка
    # фразы, а не только в начале, как было раньше.
    when_match = re.search(_REMINDER_WHEN, rest, re.I)
    if not when_match:
        return None, None
    when = when_match.group(0).strip()
    reminder_text = rest[:when_match.start()] + " " + rest[when_match.end():]
    reminder_text = re.sub(r"\s+", " ", reminder_text).strip(" ,.")
    if not reminder_text:
        return None, None
    return reminder_text, when
 
 
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
    if "note_text" in slot_names:
        value = _extract_after_prefix(raw, ("добавь в заметки", "запиши в заметки", "сохрани в заметки", "создай заметку"))
        if value:
            result["note_text"] = value
    if "note_query" in slot_names:
        value = _extract_after_prefix(raw, ("удали заметку", "удали из заметок", "убери заметку"))
        if value:
            result["note_query"] = value
    if "reminder_text" in slot_names or "reminder_when" in slot_names:
        reminder_text, reminder_when = _extract_reminder(raw)
        if reminder_text and "reminder_text" in slot_names:
            result["reminder_text"] = reminder_text
        if reminder_when and "reminder_when" in slot_names:
            result["reminder_when"] = reminder_when
    return result
 
 
def classify_candidates(text: str, commands: list[dict], limit: int = 5) -> list[tuple[float, dict]]:
    """Возвращает до `limit` лучших команд-кандидатов с их сырым score, по
    убыванию — независимо от порога. Используется и для обычного classify()
    (limit=1), и для LLM-подстраховки, когда команда близка к порогу, но не
    дотягивает до него."""
    normalized = normalize_text(text)
    if not normalized:
        return []
    scored: dict[str, tuple[float, dict]] = {}
    for command in commands:
        for phrase in command.get("phrases", []):
            score = _score(normalized, phrase, command)
            existing = scored.get(command["id"])
            if existing is None or score > existing[0]:
                scored[command["id"]] = (score, command)
    return sorted(scored.values(), key=lambda pair: pair[0], reverse=True)[:limit]
 
 
def classify(text: str, commands: list[dict]) -> IntentResult | None:
    candidates = classify_candidates(text, commands, limit=1)
    if not candidates:
        return None
    score, command = candidates[0]
    threshold = float(command.get("threshold", 0.72))
    if score < threshold:
        return None
    slot_names = list(command.get("slots", []))
    return IntentResult(
        intent_id=command["id"],
        confidence=score,
        slots=extract_slots(text, slot_names),
    )