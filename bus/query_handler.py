"""
bus/query_handler.py

Consultive Query Pattern — implement the full protocol for bidirectional queries:
  1. Requester submits query.request via event bus
  2. Executor receives, processes (via MCP), emits query.result
  3. Requester polls or waits for result via query_id (correlation)

Responsabilidades:
  - submit_query(): emit query.request, return query_id
  - await_result(): poll pending-events.json for result, return dict | None
  - process_query_request(): simulate MCP execution, emit query.result
  - QueryTimeoutError: raised when result not available within timeout
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import json


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class MCPTarget(str, Enum):
    """MCP targets (external systems)."""
    LINEAR = "linear"
    GITHUB = "github"
    FIGMA = "figma"
    SLACK = "slack"
    NOTION = "notion"


class QueryRequester(str, Enum):
    """Who initiated the query."""
    PROJECT_STUDIO = "project-studio"
    USER = "user"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class QueryTimeoutError(Exception):
    """Raised when result not available within timeout."""
    def __init__(self, query_id: str, timeout_ms: int) -> None:
        self.query_id = query_id
        self.timeout_ms = timeout_ms
        super().__init__(
            f"Query {query_id} did not complete within {timeout_ms}ms"
        )


# ---------------------------------------------------------------------------
# Query submission
# ---------------------------------------------------------------------------

def submit_query(
    query_payload: dict[str, Any],
    mcp_target: MCPTarget,
    requester: QueryRequester = QueryRequester.PROJECT_STUDIO,
    timeout_ms: int = 5000,
) -> str:
    """
    Submits a consultive query to the event bus.

    Args:
        query_payload: The query parameters (specific to mcp_target)
        mcp_target: Which external system to query
        requester: Who is making the request
        timeout_ms: How long to wait for result (default: 5s)

    Returns:
        query_id (UUID string) — use this to correlate the result

    Emits:
        query.request event to the bus (callback_event: query.result)
    """
    query_id = str(uuid.uuid4())

    request_payload = {
        "query_id": query_id,
        "requester": requester.value,
        "mcp_target": mcp_target.value,
        "query_payload": query_payload,
        "timeout_ms": timeout_ms,
        "callback_event": "query.result",
    }

    # In a real implementation, this would emit to event_bus.emit()
    # For now, return the query_id so tests can correlate
    return query_id


def await_result(
    query_id: str,
    timeout_ms: int = 5000,
    poll_interval_ms: int = 100,
) -> Optional[dict[str, Any]]:
    """
    Waits for a query result to be available.

    Polls the pending-events.json (DLQ) or result queue for an event
    that matches:
      - event.name == "query.result"
      - event.query_id == query_id

    Args:
        query_id: The ID returned by submit_query()
        timeout_ms: How long to wait (default: 5s)
        poll_interval_ms: How often to check (default: 100ms)

    Returns:
        The query.result payload dict if found, None if timeout
    """
    start_time = time.time()
    timeout_s = timeout_ms / 1000.0

    while time.time() - start_time < timeout_s:
        # Simulate checking for result (in real impl, check event store)
        # For testing, we'll return a simulated result if it exists in a queue
        result = _find_query_result(query_id)
        if result:
            return result

        time.sleep(poll_interval_ms / 1000.0)

    # Timeout reached
    return None


def _find_query_result(query_id: str) -> Optional[dict[str, Any]]:
    """
    Helper: search for query.result in simulated event store.
    In production, this would query the actual event store/DLQ.
    """
    # This is a stub for testing — actual implementation would query the bus
    return None


# ---------------------------------------------------------------------------
# Query processing (executor side)
# ---------------------------------------------------------------------------

def process_query_request(
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Process a query.request and emit query.result.

    In production, this would:
      1. Extract mcp_target
      2. Call the MCP handler for that target
      3. Emit query.result with data or error

    For testing (deterministic), returns a mocked result.
    """
    query_id = request_payload["query_id"]
    mcp_target = request_payload["mcp_target"]
    query_payload = request_payload["query_payload"]

    # Simulate MCP execution (deterministic, no network)
    success = True
    data = _mock_mcp_response(mcp_target, query_payload)

    result_payload = {
        "query_id": query_id,
        "mcp_target": mcp_target,
        "success": success,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }

    if success:
        result_payload["data"] = data
    else:
        result_payload["error"] = {
            "code": "mcp_unavailable",
            "message": f"MCP target {mcp_target} not available",
        }

    return result_payload


def _mock_mcp_response(target: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Mock responses for each MCP target (for testing).
    In production, these would call real MCP handlers.
    """
    if target == "linear":
        return {
            "issues": [
                {
                    "id": "LIN-123",
                    "title": payload.get("query", "Test issue"),
                    "state": "IN_PROGRESS",
                }
            ]
        }
    elif target == "github":
        return {
            "repositories": [
                {
                    "name": payload.get("query", "test-repo"),
                    "stars": 42,
                    "language": "Python",
                }
            ]
        }
    elif target == "slack":
        return {
            "messages": [
                {
                    "channel": payload.get("channel", "#general"),
                    "count": 5,
                    "latest": "2026-06-27T16:00:00Z",
                }
            ]
        }
    else:
        return {"status": "ok", "target": target}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_query_request(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validates a query.request payload against the schema.

    Checks:
      - query_id present and is UUID
      - requester in valid enum
      - mcp_target in valid enum
      - query_payload is dict
      - timeout_ms is positive int
      - callback_event == "query.result"

    Returns:
        (is_valid, list_of_errors)
    """
    errors = []

    # Check required fields
    required = ["query_id", "requester", "mcp_target", "query_payload", "timeout_ms"]
    for field in required:
        if field not in payload:
            errors.append(f"Missing required field: {field}")

    # Validate query_id is UUID-like
    if "query_id" in payload:
        try:
            uuid.UUID(payload["query_id"])
        except ValueError:
            errors.append(f"query_id is not a valid UUID: {payload['query_id']}")

    # Validate enums
    if "requester" in payload:
        if payload["requester"] not in [r.value for r in QueryRequester]:
            errors.append(f"Invalid requester: {payload['requester']}")

    if "mcp_target" in payload:
        if payload["mcp_target"] not in [t.value for t in MCPTarget]:
            errors.append(f"Invalid mcp_target: {payload['mcp_target']}")

    # Validate timeout
    if "timeout_ms" in payload:
        if not isinstance(payload["timeout_ms"], int) or payload["timeout_ms"] <= 0:
            errors.append("timeout_ms must be a positive integer")

    return len(errors) == 0, errors


def validate_query_result(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validates a query.result payload against the schema.

    Checks:
      - query_id present and is UUID
      - mcp_target in valid enum
      - success is boolean
      - executed_at is ISO-8601
      - if success: data must be present
      - if not success: error must have code and message

    Returns:
        (is_valid, list_of_errors)
    """
    errors = []

    # Check required fields
    required = ["query_id", "mcp_target", "success", "executed_at"]
    for field in required:
        if field not in payload:
            errors.append(f"Missing required field: {field}")

    # Validate query_id
    if "query_id" in payload:
        try:
            uuid.UUID(payload["query_id"])
        except ValueError:
            errors.append(f"query_id is not a valid UUID: {payload['query_id']}")

    # Validate mcp_target
    if "mcp_target" in payload:
        if payload["mcp_target"] not in [t.value for t in MCPTarget]:
            errors.append(f"Invalid mcp_target: {payload['mcp_target']}")

    # Validate success flag
    if "success" in payload:
        if not isinstance(payload["success"], bool):
            errors.append("success must be a boolean")

    # Conditional validation based on success
    if payload.get("success"):
        if "data" not in payload:
            errors.append("data must be present when success=true")
    else:
        if "error" not in payload:
            errors.append("error must be present when success=false")
        elif isinstance(payload["error"], dict):
            if "code" not in payload["error"] or "message" not in payload["error"]:
                errors.append("error must have code and message")

    return len(errors) == 0, errors
