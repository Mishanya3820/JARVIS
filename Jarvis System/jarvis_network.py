"""
Проверка наличия интернет-соединения.
 
Используется, чтобы решить: обращаться к Groq (облачной LLM) или
работать в офлайн-режиме, ограничившись локальными командами.
"""
 
import socket
import time
 
# Публичные DNS-серверы — быстрый и надёжный способ проверить сеть,
# не завязываясь на доступность конкретного сайта.
_PROBE_HOSTS = [
    ("8.8.8.8", 53),   # Google DNS
    ("1.1.1.1", 53),   # Cloudflare DNS
]
 
_CACHE_SECONDS = 3.0
_last_check_time = 0.0
_last_result = False
 
 
def _probe(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
 
 
def is_online(timeout: float = 1.2, use_cache: bool = True) -> bool:
    """Возвращает True, если есть доступ в интернет.
 
    Результат кэшируется на короткое время (по умолчанию 3 секунды),
    чтобы не делать лишний сетевой запрос на каждое слово/команду —
    этого достаточно, чтобы отслеживать реальные обрывы связи, но не
    замедлять каждый вызов process_message.
    """
    global _last_check_time, _last_result
 
    now = time.monotonic()
    if use_cache and (now - _last_check_time) < _CACHE_SECONDS:
        return _last_result
 
    result = any(_probe(host, port, timeout) for host, port in _PROBE_HOSTS)
 
    _last_check_time = now
    _last_result = result
    return result