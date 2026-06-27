"""
bus/retry.py

Retry policy implementation — backoff exponencial com jitter, TTL na DLQ,
e reprocessamento automático de eventos pendentes.

Responsabilidades:
  - calculate_backoff(): calcula delay exponencial (1s, 2s, 4s, 8s, 16s)
  - should_retry(): decide se evento deve fazer retry baseado em retry_count vs max_attempts
  - should_expire(): decide se evento expirou baseado em TTL
  - expired_entries(): filtra eventos que já passaram do TTL
  - next_retry_time(): calcula quando um evento deve ser reprocessado
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Backoff strategies
# ---------------------------------------------------------------------------

def calculate_backoff(
    retry_count: int,
    backoff_strategy: str,
    max_delay: float = 60.0,
    jitter: bool = True,
) -> float:
    """
    Calcula delay antes do próximo retry.

    Args:
        retry_count: numero de tentativas ja feitas (0-based: primeiro retry = 0)
        backoff_strategy: 'exponential' ou 'linear'
        max_delay: delay maximo em segundos (default: 60s)
        jitter: adiciona randomizacao (±20%) para evitar thundering herd

    Returns:
        Delay em segundos.

    Exemplos:
        - exponential, retry 0: 1s
        - exponential, retry 1: 2s (+ jitter)
        - exponential, retry 2: 4s (+ jitter)
        - linear, retry 0-N: 5s (+ jitter)
    """
    if backoff_strategy == "exponential":
        # 2^(retry_count + 1) = 2, 4, 8, 16, 32, ...
        base_delay = 2 ** (retry_count + 1)
    elif backoff_strategy == "linear":
        # 5s flat para linear
        base_delay = 5.0
    else:
        # Fallback: nao faz retry
        return 0.0

    # Limitar ao max_delay
    delay = min(base_delay, max_delay)

    # Adicionar jitter: ±20%
    if jitter:
        jitter_range = delay * 0.2
        delay += random.uniform(-jitter_range, jitter_range)
        delay = max(0, delay)  # Nao permitir delay negativo

    return delay


def should_retry(retry_count: int, max_attempts: int) -> bool:
    """
    Decide se um evento ainda pode fazer retry.

    Args:
        retry_count: tentativas ja feitas (0-based)
        max_attempts: maximo permitido

    Returns:
        True se retry_count < max_attempts, False caso contrario.
    """
    return retry_count < max_attempts


def should_expire(queued_at: str, ttl_hours: int) -> bool:
    """
    Decide se um evento expirou baseado no TTL.

    Args:
        queued_at: ISO-8601 timestamp quando foi enfileirado
        ttl_hours: Time-To-Live em horas

    Returns:
        True se (agora - queued_at) >= ttl_hours.
    """
    now = datetime.now(timezone.utc)
    queued_dt = datetime.fromisoformat(queued_at)

    # Se queued_at nao tem timezone, assume UTC
    if queued_dt.tzinfo is None:
        queued_dt = queued_dt.replace(tzinfo=timezone.utc)

    ttl_delta = timedelta(hours=ttl_hours)
    return (now - queued_dt) >= ttl_delta


def expired_entries(dlq_pending: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Filtra eventos que expiram TTL.

    Cada entrada deve ter 'queued_at' e um campo 'ttl_hours' no payload.
    Retorna lista de entradas que devem ser removidas da DLQ.
    """
    expired = []
    for entry in dlq_pending:
        queued_at = entry.get("queued_at", "")
        ttl_hours = entry.get("ttl_hours", 24)
        if should_expire(queued_at, ttl_hours):
            expired.append(entry)
    return expired


def next_retry_time(
    entry: dict[str, Any],
    routing_table: dict[str, Any],
) -> datetime | None:
    """
    Calcula quando um evento deve ser reprocessado.

    Args:
        entry: DLQ entry com event_id, retry_count, queued_at
        routing_table: routing-table.yaml loaded

    Returns:
        datetime UTC quando reprocessar, ou None se nao deve fazer retry.
    """
    event_name = entry["event"].get("name") if "event" in entry else None
    if not event_name or event_name not in routing_table["events"]:
        return None

    route = routing_table["events"][event_name]
    retry_policy = route.get("retry_policy", {})
    backoff_strategy = retry_policy.get("backoff", "linear")
    max_attempts = retry_policy.get("max_attempts", 3)
    retry_count = entry.get("retry_count", 0)

    # Se ja atingiu max_attempts, nao retry
    if not should_retry(retry_count, max_attempts):
        return None

    # Calcular delay
    delay_seconds = calculate_backoff(retry_count, backoff_strategy)

    # Calcular tempo do proximo retry
    queued_dt = datetime.fromisoformat(entry["queued_at"])
    if queued_dt.tzinfo is None:
        queued_dt = queued_dt.replace(tzinfo=timezone.utc)

    # Usar o tempo do ultimo retry (ou queued_at se primeiro retry)
    last_retry = entry.get("last_retry_at")
    if last_retry:
        last_retry_dt = datetime.fromisoformat(last_retry)
        if last_retry_dt.tzinfo is None:
            last_retry_dt = last_retry_dt.replace(tzinfo=timezone.utc)
    else:
        last_retry_dt = queued_dt

    next_time = last_retry_dt + timedelta(seconds=delay_seconds)
    return next_time


# ---------------------------------------------------------------------------
# Readiness check
# ---------------------------------------------------------------------------

def ready_for_retry(
    entry: dict[str, Any],
    routing_table: dict[str, Any],
    now: datetime | None = None,
) -> bool:
    """
    Decide se um evento esta pronto para ser reprocessado agora.

    Args:
        entry: DLQ entry
        routing_table: routing-table.yaml
        now: datetime atual (default: agora)

    Returns:
        True se entry pode ser reprocessado imediatamente.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Verificar se nao expirou TTL
    ttl_hours = entry.get("ttl_hours", 24)
    if should_expire(entry["queued_at"], ttl_hours):
        return False

    # Calcular next_retry_time
    next_time = next_retry_time(entry, routing_table)
    if next_time is None:
        return False

    # Pronto se agora >= next_retry_time
    return now >= next_time
