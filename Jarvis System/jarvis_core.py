"""Основное ядро JARVIS.
 
Маршрут обработки:
    Vosk -> local intent -> local command
                         -> Groq, если локальная команда не найдена
"""
 
from __future__ import annotations
 
import json
import queue
import threading
import re
import subprocess
import webbrowser
from urllib.parse import quote
 
from groq import Groq
 
from jarvis_network import is_online
from jarvis_settings import get_groq_api_key, load_settings
from jarvis_voice import SOUND_NOT_FOUND
from jarvis_commands import match_local_command as _match_command
from jarvis_commands import execute_local_command
 
 
GROQ_MODEL = load_settings().get("groq_model", "openai/gpt-oss-120b")
_groq_client: Groq | None = None
 
 
def normalize_text(text: str) -> str:
    """Нормализует текст для локальных проверок GUI."""
    text = (text or "").lower().replace("ё", "е")
    text = re.sub(r"[^a-zа-я0-9\s]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()
 
 
def get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        api_key = get_groq_api_key()
        if not api_key:
            raise RuntimeError(
                "Не найден Groq API-ключ. Откройте Настройки и добавьте API-ключ."
            )
        _groq_client = Groq(api_key=api_key)
    return _groq_client
 
 
def reset_groq_client() -> None:
    """Сбрасывает закэшированный клиент после изменения API-ключа."""
    global _groq_client
    _groq_client = None
 
 
def set_groq_model(model_name: str) -> None:
    global GROQ_MODEL
    GROQ_MODEL = model_name
 
 
# ============================================================
# ИНСТРУМЕНТЫ ДЛЯ GROQ
# ============================================================
 
def open_notepad() -> str:
    subprocess.Popen(["notepad.exe"])
    return "Блокнот успешно открыт."
 
 
def open_calculator() -> str:
    subprocess.Popen(["calc.exe"])
    return "Калькулятор успешно открыт."
 
 
def open_browser(url: str = "https://www.google.com") -> str:
    if not str(url).startswith(("http://", "https://")):
        url = "https://" + str(url)
    webbrowser.open(str(url))
    return f"Браузер открыт, адрес: {url}"
 
 
def search_web(query: str) -> str:
    webbrowser.open(f"https://www.google.com/search?q={quote(str(query))}")
    return f"Выполнен поиск: {query}"
 
 
def open_app(app_name: str) -> str:
    try:
        import os
        os.startfile(app_name)
        return f"Приложение '{app_name}' запущено."
    except Exception as e:
        return f"Не удалось открыть '{app_name}': {e}"
 
 
def open_path(path: str) -> str:
    try:
        import os
        os.startfile(os.path.expandvars(os.path.expanduser(path)))
        return f"Путь открыт: {path}"
    except Exception as e:
        return f"Не удалось открыть '{path}': {e}"
 
 
def run_command(command: str) -> str:
    try:
        result = subprocess.run(
            ["cmd.exe", "/c", command],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (result.stdout or "").strip()
        error = (result.stderr or "").strip()
        if result.returncode == 0:
            return f"Команда выполнена успешно.\n{output}" if output else "Команда выполнена успешно."
        return f"Команда завершилась с ошибкой:\n{error or output}"
    except subprocess.TimeoutExpired:
        return "Команда выполняется слишком долго и была прервана."
    except Exception as e:
        return f"Ошибка выполнения команды: {e}"
 
 
def run_command_async(command: str, on_done=None) -> str:
    def _worker():
        result = run_command(command)
        if on_done:
            on_done(result)
 
    threading.Thread(target=_worker, daemon=True).start()
    return "Выполняю команду."
 
 
TOOLS_BY_NAME = {
    "open_notepad": open_notepad,
    "open_calculator": open_calculator,
    "open_browser": open_browser,
    "search_web": search_web,
    "open_app": open_app,
    "open_path": open_path,
    "run_command": run_command,
}
 
 
TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "open_notepad", "description": "Открывает Блокнот Windows.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "open_calculator", "description": "Открывает Калькулятор Windows.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "open_browser", "description": "Открывает браузер по указанному адресу.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "search_web", "description": "Открывает браузер и ищет информацию в Google.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "open_app", "description": "Открывает приложение Windows по имени или пути.", "parameters": {"type": "object", "properties": {"app_name": {"type": "string"}}, "required": ["app_name"]}}},
    {"type": "function", "function": {"name": "open_path", "description": "Открывает файл или папку Windows.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "run_command", "description": "Выполняет команду cmd.exe, когда другие инструменты не подходят.", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
]
 
 
# ============================================================
# ЛОКАЛЬНЫЕ КОМАНДЫ
# ============================================================
 
def match_local_command(user_text: str, grammar_text: str | None = None):
    """Совместимый интерфейс: возвращает текст результата и факт совпадения.
 
    Если передан grammar_text (результат грамматически-ограниченного
    прохода Vosk — см. jarvis_voice.listen), он проверяется первым: раз
    распознаватель был ограничен списком именно известных команд и всё
    равно уверенно выбрал одну из них, это куда надёжнее, чем гадать по
    свободному тексту, который мог "поплыть" на незнакомых словах вроде
    "дискорд"/"стим". Свободный текст остаётся резервным вариантом —
    когда grammar_text пуст (сказано что-то, не похожее ни на одну
    команду) или отсутствует (например, команда пришла из текстового
    поля, а не голосом).
    """
    for candidate in (grammar_text, user_text):
        if not candidate:
            continue
        match = _match_command(candidate)
        if match is not None:
            print(f"[LOCAL INTENT] {match.result.intent_id} ({match.result.confidence * 100:.1f}%) "
                  f"slots={match.result.slots} источник={'grammar' if candidate == grammar_text else 'free'}")
            result = execute_local_command(match)
            if not result.get("ok"):
                return result.get("message", "Не удалось выполнить команду."), True
            return result.get("message", f"Команда '{match.result.intent_id}' выполнена."), True
 
    return None, False
 
 
SYSTEM_PROMPT = """
Ты — JARVIS, персональный компьютерный ассистент пользователя.
 
Твои качества: вежливый, спокойный, уверенный, умный и краткий.
 
Правила:
- Локальные команды компьютера уже обрабатываются программой до тебя.
- Если пользователь задаёт обычный вопрос, отвечай непосредственно.
- Если для сложного действия подходит доступный инструмент, используй его.
- run_command используй только когда другие инструменты не подходят.
- Не утверждай, что действие выполнено, если инструмент сообщил об ошибке.
- Отвечай кратко, потому что ответ будет озвучен голосом.
"""
 
messages = [{"role": "system", "content": SYSTEM_PROMPT}]
 
 
def warmup() -> None:
    client = get_groq_client()
    client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": "Ответь одним словом: готов."}],
        max_tokens=10,
    )
 
 
def _call_groq_stream(msgs):
    return get_groq_client().chat.completions.create(
        model=GROQ_MODEL,
        messages=msgs,
        tools=TOOL_SCHEMAS,
        stream=True,
    )
 
 
_SENTENCE_END_RE = re.compile(r"(?<=[.!?…])\s+")
 
 
def process_message(user_text: str, grammar_text: str | None = None, on_speak_ready=None) -> dict:
    """Сначала выполняет локальный intent (с приоритетом grammar_text
    над свободным текстом, см. match_local_command), затем при
    необходимости Groq."""
    local_result, local_matched = match_local_command(user_text, grammar_text)
    if local_matched:
        return {"type": "local", "text": local_result or "Команда выполнена."}
 
    if not is_online():
        print("[OFFLINE] Локальная команда не найдена.")
        return {"type": "sound", "path": SOUND_NOT_FOUND}
 
    messages.append({"role": "user", "content": user_text})
 
    speech_queue = queue.Queue() if on_speak_ready else None
    speaker_thread = None
 
    if speech_queue is not None:
        def _speaker_worker():
            while True:
                sentence = speech_queue.get()
                if sentence is None:
                    break
                try:
                    on_speak_ready(sentence)
                except Exception as e:
                    print(f"[Ошибка озвучки потокового ответа] {e}")
 
        speaker_thread = threading.Thread(target=_speaker_worker, daemon=True)
        speaker_thread.start()
 
    def _stop_speaker():
        if speech_queue is not None:
            speech_queue.put(None)
        if speaker_thread is not None:
            speaker_thread.join()
 
    try:
        while True:
            try:
                stream = _call_groq_stream(messages)
            except Exception as e:
                print(f"[Ошибка запроса к Groq] {e}")
                if messages and messages[-1].get("role") == "user":
                    messages.pop()
                _stop_speaker()
                return {"type": "sound", "path": SOUND_NOT_FOUND}
 
            content_buffer = ""
            spoken_up_to = 0
            tool_calls_acc = {}
 
            try:
                for chunk in stream:
                    delta = chunk.choices[0].delta
 
                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            entry = tool_calls_acc.setdefault(tc_delta.index, {"id": None, "name": None, "arguments": ""})
                            if tc_delta.id:
                                entry["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    entry["name"] = tc_delta.function.name
                                if tc_delta.function.arguments:
                                    entry["arguments"] += tc_delta.function.arguments
 
                    if delta.content:
                        content_buffer += delta.content
                        if speech_queue is not None and not tool_calls_acc:
                            remainder = content_buffer[spoken_up_to:]
                            parts = _SENTENCE_END_RE.split(remainder)
                            if len(parts) > 1:
                                spoken_up_to += len(remainder) - len(parts[-1])
                                for sentence in parts[:-1]:
                                    sentence = sentence.strip()
                                    if sentence:
                                        speech_queue.put(sentence)
            except Exception as e:
                print(f"[Ошибка чтения потока Groq] {e}")
                _stop_speaker()
                return {"type": "sound", "path": SOUND_NOT_FOUND}
 
            if tool_calls_acc:
                messages.append({
                    "role": "assistant",
                    "content": content_buffer or None,
                    "tool_calls": [
                        {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                        for tc in tool_calls_acc.values()
                    ],
                })
 
                for tc in tool_calls_acc.values():
                    function_name = tc["name"]
                    try:
                        function_args = json.loads(tc["arguments"] or "{}")
                    except json.JSONDecodeError:
                        function_args = {}
 
                    tool_func = TOOLS_BY_NAME.get(function_name)
                    if tool_func is None:
                        result = "Ошибка: неизвестный инструмент."
                    else:
                        try:
                            if function_name == "run_command":
                                result = run_command_async(**function_args)
                            else:
                                result = tool_func(**function_args)
                        except Exception as tool_error:
                            result = f"Ошибка при выполнении инструмента '{function_name}': {tool_error}"
 
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": str(result)})
 
                continue
 
            tail = content_buffer[spoken_up_to:].strip()
            if speech_queue is not None and tail:
                speech_queue.put(tail)
 
            messages.append({"role": "assistant", "content": content_buffer})
            _stop_speaker()
 
            if speech_queue is not None:
                return {"type": "streamed", "text": content_buffer}
            return {"type": "text", "text": content_buffer}
 
    except Exception:
        _stop_speaker()
        raise
