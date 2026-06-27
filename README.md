# nerve-layer

Event schema and bus for the **Project Nerve** ecosystem.

The Nerve Layer is the communication backbone between:
- **project-studio** - governance UI (PM + Tech Lead)
- **agent-dev-harness** - autonomous coding agent
- **context-adapter** - translates Brief to platform-specific config

---

## Repository structure

```text
nerve-layer/
  schemas/
    event.schema.yaml          # Base event envelope (JSON Schema Draft 2020-12)
    events/                    # Per-event typed payload schemas (13 types)
  routing-table.yaml           # Subscribers, retry policy, DLQ config per event
  bus/
    pending-events.json        # Dead Letter Queue (MVP: file-based)
    event_bus.py               # emit / drain / ack / increment_retry
  validator/
    validate.py                # validate_event / validate_payload_only
  tests/
    fixtures/
    test_schema_validation.py  # 26 tests
  pyproject.toml
```text

---

## 13 event types

| Event | Priority | requires_human |
|---|---|---|
| brief.published | high | false |
| adr.approved | high | true |
| adr.superseded | normal | true |
| adr.stale | normal | true |
| design.component.changed | normal | false |
| design.token.updated | normal | false |
| harness.task.complete | normal | false |
| harness.task.blocked | high | true |
| feature.scope.alert | high | true |
| skill.updated | low | false |
| adapter.fidelity.report | high | true |
| query.request | normal | false |
| query.result | normal | false |

---

## Quick start

```bash
pip install jsonschema pyyaml pytest
pytest tests/ -v
```bash

---

## How to add a new event

1. Add name to `event.schema.yaml` enum
2. Create `schemas/events/<name>.yaml` with payload schema
3. Add route in `routing-table.yaml`
4. Add tests in `tests/test_schema_validation.py`
5. Bump `schema_version` (MINOR if new event, PATCH if fix)

---

*Part of Project Nerve - LLM governance ecosystem.*
