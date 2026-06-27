"""
validate.py — Nerve Layer · Event Schema Validator

Valida um evento contra:
  1. event.schema.yaml (envelope base)
  2. schemas/events/<event.name>.yaml (payload específico)

Levanta ValidationError imediatamente se qualquer campo obrigatório
estiver ausente ou com tipo incorreto — o bus não roteia eventos inválidos.

Dependências: jsonschema, pyyaml
  pip install jsonschema pyyaml
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, ValidationError as JsonSchemaError
from jsonschema.exceptions import SchemaError

_ROOT = Path(__file__).parent.parent
_BASE_SCHEMA_PATH = _ROOT / "schemas" / "event.schema.yaml"
_EVENTS_DIR = _ROOT / "schemas" / "events"


class ValidationError(Exception):
    """Levantada quando um evento não conforma o schema."""


def validate_event(event: dict[str, Any]) -> None:
    """
    Valida o evento completo.

    Passos:
      1. Valida envelope contra event.schema.yaml
      2. Valida payload contra schemas/events/<name>.yaml

    Levanta ValidationError com mensagem descritiva se inválido.
    """
    _validate_against_schema(event, _load_base_schema(), context="envelope")
    _validate_payload(event)


def validate_payload_only(event_name: str, payload: dict[str, Any]) -> None:
    """
    Valida apenas o payload de um evento específico.
    Útil para validação parcial antes de montar o envelope completo.
    """
    schema = _load_payload_schema(event_name)
    _validate_against_schema(payload, schema, context=f"payload({event_name})")


# ── Private ─────────────────────────────────────────────────────

def _validate_against_schema(
    data: dict[str, Any],
    schema: dict[str, Any],
    context: str,
) -> None:
    try:
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
        if errors:
            messages = [_format_error(e) for e in errors]
            raise ValidationError(
                f"Schema validation failed [{context}]:\n" + "\n".join(messages)
            )
    except SchemaError as e:
        raise ValidationError(f"Invalid schema [{context}]: {e.message}") from e


def _validate_payload(event: dict[str, Any]) -> None:
    event_name = event.get("name")
    if not event_name:
        raise ValidationError("Event 'name' is required")

    payload = event.get("payload")
    if payload is None:
        raise ValidationError("Event 'payload' is required")

    schema = _load_payload_schema(event_name)
    _validate_against_schema(payload, schema, context=f"payload({event_name})")


def _load_base_schema() -> dict[str, Any]:
    if not _BASE_SCHEMA_PATH.exists():
        raise ValidationError(f"Base schema not found: {_BASE_SCHEMA_PATH}")
    with open(_BASE_SCHEMA_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_payload_schema(event_name: str) -> dict[str, Any]:
    schema_path = _EVENTS_DIR / f"{event_name}.yaml"
    if not schema_path.exists():
        raise ValidationError(
            f"No payload schema found for event '{event_name}'. "
            f"Expected: {schema_path}. "
            f"Add the event name to event.schema.yaml enum and create the schema file."
        )
    with open(schema_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _format_error(error: JsonSchemaError) -> str:
    path = " → ".join(str(p) for p in error.path) if error.path else "root"
    return f"  [{path}] {error.message}"
