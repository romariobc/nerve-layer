"""
event_bus.py — Nerve Layer · Event Bus (MVP local implementation)

Responsabilidades:
  - emit(event): valida schema e grava no event-log + enfileira para subscribers
  - drain(subscriber): retorna eventos pendentes para um subscriber e remove da DLQ
  - ack(event_id, subscriber): confirma entrega, remove da DLQ
  - _load_routing(): lê routing-table.yaml

MVP local: usa pending-events.json como DLQ em vez de broker externo.
Produção: substituir por implementação que usa Redis, RabbitMQ ou similar —
          as assinaturas públicas (emit/drain/ack) permanecem as mesmas.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from validator.validate import validate_event, ValidationError

_ROOT = Path(__file__).parent.parent
_DLQ_PATH = _ROOT / "bus" / "pending-events.json"
_ROUTING_PATH = _ROOT / "routing-table.yaml"
_LOG_PATH = _ROOT / "bus" / "event-log.jsonl"


# ── Public API ──────────────────────────────────────────────────

def emit(event: dict[str, Any]) -> str:
    """
    Valida e emite um evento.

    Preenche automaticamente:
      - id (se ausente): UUID v4
      - timestamp (se ausente): UTC agora
      - routing: derivado do routing-table.yaml
      - meta.schema_version: versão atual do schema
      - meta.retry_count: 0 (novo evento)

    Retorna o event_id.
    Levanta ValidationError se o evento não conforma o schema.
    """
    routing_table = _load_routing()
    event_name = event.get("name")

    if event_name not in routing_table["events"]:
        raise ValidationError(f"Event '{event_name}' not in routing-table.yaml")

    route = routing_table["events"][event_name]

    # Preencher campos automáticos
    event.setdefault("id", str(uuid.uuid4()))
    event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    event.setdefault("routing", {
        "subscribers": route["subscribers"],
        "requires_human": route["requires_human"],
        "priority": route["priority"],
    })
    event.setdefault("meta", {})
    event["meta"].setdefault("schema_version", _current_schema_version())
    event["meta"].setdefault("retry_count", 0)

    # Validar
    validate_event(event)

    # Gravar no log imutável
    _append_log(event)

    # Enfileirar na DLQ para cada subscriber que precisa de retry/replay
    if route.get("dead_letter_queue", False):
        _enqueue_dlq(event, route["subscribers"], route)

    return event["id"]


def drain(subscriber: str) -> list[dict[str, Any]]:
    """
    Retorna todos os eventos pendentes para um subscriber.
    Chamado pelo subscriber ao iniciar sessão (replay_on_connect).
    NÃO remove da DLQ — use ack() após processar.
    """
    dlq = _load_dlq()
    return [
        entry for entry in dlq["pending"]
        if subscriber in entry["subscribers"]
        and not entry.get("acked_by", {}).get(subscriber, False)
    ]


def ack(event_id: str, subscriber: str) -> None:
    """
    Confirma entrega de um evento para um subscriber.
    Remove da DLQ quando todos os subscribers confirmaram.
    """
    dlq = _load_dlq()
    for entry in dlq["pending"]:
        if entry["event_id"] == event_id:
            entry.setdefault("acked_by", {})[subscriber] = True
            # Remove se todos os subscribers confirmaram
            if all(entry["acked_by"].get(s, False) for s in entry["subscribers"]):
                dlq["pending"].remove(entry)
            break
    _save_dlq(dlq)


def increment_retry(event_id: str) -> int:
    """
    Incrementa retry_count de um evento na DLQ.
    Retorna o novo retry_count.
    Remove da DLQ se max_attempts foi atingido.
    """
    routing_table = _load_routing()
    dlq = _load_dlq()

    for entry in dlq["pending"]:
        if entry["event_id"] == event_id:
            entry["retry_count"] = entry.get("retry_count", 0) + 1
            event_name = entry["event"]["name"]
            max_attempts = routing_table["events"][event_name]["retry_policy"]["max_attempts"]
            if entry["retry_count"] >= max_attempts:
                dlq["pending"].remove(entry)
                _save_dlq(dlq)
                return entry["retry_count"]
            _save_dlq(dlq)
            return entry["retry_count"]

    return 0


# ── Private ─────────────────────────────────────────────────────

def _load_routing() -> dict[str, Any]:
    with open(_ROUTING_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_dlq() -> dict[str, Any]:
    if not _DLQ_PATH.exists():
        return {"schema_version": "1.0.0", "pending": []}
    with open(_DLQ_PATH, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("pending", [])
    return data


def _save_dlq(dlq: dict[str, Any]) -> None:
    _DLQ_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_DLQ_PATH, "w", encoding="utf-8") as f:
        json.dump(dlq, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _append_log(event: dict[str, Any]) -> None:
    """Grava evento no log imutável (append-only JSONL)."""
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _enqueue_dlq(
    event: dict[str, Any],
    subscribers: list[str],
    route: dict[str, Any],
) -> None:
    """Adiciona evento à DLQ para subscribers que usam retry/replay."""
    dlq = _load_dlq()

    # Evitar duplicata por idempotency key
    if any(e["event_id"] == event["id"] for e in dlq["pending"]):
        return

    dlq["pending"].append({
        "event_id": event["id"],
        "event": event,
        "subscribers": subscribers,
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "retry_count": 0,
        "acked_by": {},
        "ttl_hours": route.get("ttl_hours", 24),
    })
    _save_dlq(dlq)


def _current_schema_version() -> str:
    """Lê schema_version do event.schema.yaml."""
    schema_path = _ROOT / "schemas" / "event.schema.yaml"
    with open(schema_path, encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith("# VERSION:"):
                return line.split(":", 1)[1].strip()
    return "1.0.0"
