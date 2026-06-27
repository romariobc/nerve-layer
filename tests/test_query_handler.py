"""
tests/test_query_handler.py

Query handler tests — consultive query pattern with correlation.

Coverage:
  - Query submission: generates UUID, returns query_id
  - Result correlation: query_id matches request to result
  - Timeout: await_result returns None after timeout
  - Request validation: required fields, UUID format, enum values
  - Result validation: success flag, data/error presence
  - Mock MCP responses: linear, github, slack, etc.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from uuid import UUID

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from bus.query_handler import (
    MCPTarget,
    QueryRequester,
    QueryTimeoutError,
    submit_query,
    await_result,
    process_query_request,
    validate_query_request,
    validate_query_result,
)


# ---------------------------------------------------------------------------
# Query submission
# ---------------------------------------------------------------------------

class TestQuerySubmission:
    def test_submit_query_returns_uuid(self):
        query_id = submit_query(
            query_payload={"search": "bug reports"},
            mcp_target=MCPTarget.LINEAR,
        )
        # Should be valid UUID
        UUID(query_id)
        assert len(query_id) == 36  # UUID string format

    def test_submit_query_with_custom_requester(self):
        query_id = submit_query(
            query_payload={"channel": "#general"},
            mcp_target=MCPTarget.SLACK,
            requester=QueryRequester.USER,
        )
        assert query_id is not None

    def test_submit_query_with_custom_timeout(self):
        query_id = submit_query(
            query_payload={"query": "test"},
            mcp_target=MCPTarget.GITHUB,
            timeout_ms=10000,
        )
        assert query_id is not None


# ---------------------------------------------------------------------------
# Result await (with timeout)
# ---------------------------------------------------------------------------

class TestAwaitResult:
    def test_await_result_timeout_returns_none(self):
        # No result enqueued, so should timeout
        result = await_result(
            query_id="00000000-0000-0000-0000-000000000000",
            timeout_ms=100,  # Short timeout
            poll_interval_ms=50,
        )
        assert result is None

    def test_await_result_respects_timeout(self):
        start = time.time()
        await_result(
            query_id="nonexistent",
            timeout_ms=200,
            poll_interval_ms=50,
        )
        elapsed = time.time() - start
        # Should have waited ~200ms, allow 50ms margin
        assert elapsed >= 0.15


# ---------------------------------------------------------------------------
# Query request validation
# ---------------------------------------------------------------------------

class TestValidateQueryRequest:
    def test_valid_request(self):
        request = {
            "query_id": "550e8400-e29b-41d4-a716-446655440000",
            "requester": "project-studio",
            "mcp_target": "linear",
            "query_payload": {"search": "bug"},
            "timeout_ms": 5000,
        }
        is_valid, errors = validate_query_request(request)
        assert is_valid
        assert errors == []

    def test_missing_required_field(self):
        request = {
            "query_id": "550e8400-e29b-41d4-a716-446655440000",
            "mcp_target": "linear",
            # Missing requester
            "query_payload": {"search": "bug"},
            "timeout_ms": 5000,
        }
        is_valid, errors = validate_query_request(request)
        assert not is_valid
        assert any("requester" in e for e in errors)

    def test_invalid_query_id_format(self):
        request = {
            "query_id": "not-a-uuid",
            "requester": "project-studio",
            "mcp_target": "linear",
            "query_payload": {"search": "bug"},
            "timeout_ms": 5000,
        }
        is_valid, errors = validate_query_request(request)
        assert not is_valid
        assert any("UUID" in e for e in errors)

    def test_invalid_requester_enum(self):
        request = {
            "query_id": "550e8400-e29b-41d4-a716-446655440000",
            "requester": "invalid-requester",
            "mcp_target": "linear",
            "query_payload": {"search": "bug"},
            "timeout_ms": 5000,
        }
        is_valid, errors = validate_query_request(request)
        assert not is_valid
        assert any("requester" in e for e in errors)

    def test_invalid_mcp_target_enum(self):
        request = {
            "query_id": "550e8400-e29b-41d4-a716-446655440000",
            "requester": "project-studio",
            "mcp_target": "invalid-mcp",
            "query_payload": {"search": "bug"},
            "timeout_ms": 5000,
        }
        is_valid, errors = validate_query_request(request)
        assert not is_valid
        assert any("mcp_target" in e for e in errors)

    def test_invalid_timeout_negative(self):
        request = {
            "query_id": "550e8400-e29b-41d4-a716-446655440000",
            "requester": "project-studio",
            "mcp_target": "linear",
            "query_payload": {"search": "bug"},
            "timeout_ms": -1,
        }
        is_valid, errors = validate_query_request(request)
        assert not is_valid
        assert any("timeout_ms" in e for e in errors)

    def test_invalid_timeout_zero(self):
        request = {
            "query_id": "550e8400-e29b-41d4-a716-446655440000",
            "requester": "project-studio",
            "mcp_target": "linear",
            "query_payload": {"search": "bug"},
            "timeout_ms": 0,
        }
        is_valid, errors = validate_query_request(request)
        assert not is_valid


# ---------------------------------------------------------------------------
# Query result validation
# ---------------------------------------------------------------------------

class TestValidateQueryResult:
    def test_valid_success_result(self):
        result = {
            "query_id": "550e8400-e29b-41d4-a716-446655440000",
            "mcp_target": "linear",
            "success": True,
            "executed_at": "2026-06-27T16:00:00Z",
            "data": {"issues": [{"id": "LIN-123", "title": "Bug"}]},
        }
        is_valid, errors = validate_query_result(result)
        assert is_valid
        assert errors == []

    def test_valid_error_result(self):
        result = {
            "query_id": "550e8400-e29b-41d4-a716-446655440000",
            "mcp_target": "linear",
            "success": False,
            "executed_at": "2026-06-27T16:00:00Z",
            "error": {
                "code": "mcp_unavailable",
                "message": "Linear MCP is offline",
            },
        }
        is_valid, errors = validate_query_result(result)
        assert is_valid
        assert errors == []

    def test_missing_data_when_success(self):
        result = {
            "query_id": "550e8400-e29b-41d4-a716-446655440000",
            "mcp_target": "linear",
            "success": True,
            "executed_at": "2026-06-27T16:00:00Z",
            # Missing data
        }
        is_valid, errors = validate_query_result(result)
        assert not is_valid
        assert any("data" in e for e in errors)

    def test_missing_error_when_failure(self):
        result = {
            "query_id": "550e8400-e29b-41d4-a716-446655440000",
            "mcp_target": "linear",
            "success": False,
            "executed_at": "2026-06-27T16:00:00Z",
            # Missing error
        }
        is_valid, errors = validate_query_result(result)
        assert not is_valid
        assert any("error" in e for e in errors)

    def test_error_missing_code(self):
        result = {
            "query_id": "550e8400-e29b-41d4-a716-446655440000",
            "mcp_target": "linear",
            "success": False,
            "executed_at": "2026-06-27T16:00:00Z",
            "error": {"message": "Error occurred"},  # Missing code
        }
        is_valid, errors = validate_query_result(result)
        assert not is_valid
        assert any("code" in e or "message" in e for e in errors)


# ---------------------------------------------------------------------------
# Query processing (mock MCP responses)
# ---------------------------------------------------------------------------

class TestProcessQueryRequest:
    def test_process_linear_query(self):
        request = {
            "query_id": "550e8400-e29b-41d4-a716-446655440000",
            "requester": "project-studio",
            "mcp_target": "linear",
            "query_payload": {"search": "bug reports"},
            "timeout_ms": 5000,
        }
        result = process_query_request(request)

        # Validate result
        is_valid, errors = validate_query_result(result)
        assert is_valid, f"Result invalid: {errors}"

        # Check correlation
        assert result["query_id"] == request["query_id"]
        assert result["mcp_target"] == "linear"
        assert result["success"] is True
        assert "data" in result
        assert "issues" in result["data"]

    def test_process_github_query(self):
        request = {
            "query_id": "550e8400-e29b-41d4-a716-446655440000",
            "requester": "project-studio",
            "mcp_target": "github",
            "query_payload": {"search": "ai-frameworks"},
            "timeout_ms": 5000,
        }
        result = process_query_request(request)

        assert result["success"] is True
        assert "repositories" in result["data"]
        assert any(r.get("name") for r in result["data"]["repositories"])

    def test_process_slack_query(self):
        request = {
            "query_id": "550e8400-e29b-41d4-a716-446655440000",
            "requester": "user",
            "mcp_target": "slack",
            "query_payload": {"channel": "#general"},
            "timeout_ms": 5000,
        }
        result = process_query_request(request)

        assert result["success"] is True
        assert "messages" in result["data"]
        assert result["data"]["messages"][0]["channel"] == "#general"

    def test_result_has_executed_at_iso_format(self):
        request = {
            "query_id": "550e8400-e29b-41d4-a716-446655440000",
            "requester": "project-studio",
            "mcp_target": "linear",
            "query_payload": {},
            "timeout_ms": 5000,
        }
        result = process_query_request(request)

        # Check ISO-8601 format
        assert "T" in result["executed_at"]
        assert "Z" in result["executed_at"]


# ---------------------------------------------------------------------------
# End-to-end correlation
# ---------------------------------------------------------------------------

class TestCorrelation:
    def test_query_result_correlates_by_id(self):
        # Step 1: Submit query
        query_id = submit_query(
            query_payload={"search": "test"},
            mcp_target=MCPTarget.LINEAR,
        )

        # Step 2: Process the query (simulate executor)
        request = {
            "query_id": query_id,
            "requester": "project-studio",
            "mcp_target": "linear",
            "query_payload": {"search": "test"},
            "timeout_ms": 5000,
        }
        result = process_query_request(request)

        # Step 3: Verify correlation
        assert result["query_id"] == query_id
        assert result["query_id"] == request["query_id"]

    def test_multiple_concurrent_queries_not_cross_correlated(self):
        # Submit two queries
        query_id_1 = submit_query(
            query_payload={"search": "A"},
            mcp_target=MCPTarget.LINEAR,
        )
        query_id_2 = submit_query(
            query_payload={"search": "B"},
            mcp_target=MCPTarget.GITHUB,
        )

        # Verify they have different IDs
        assert query_id_1 != query_id_2
        assert UUID(query_id_1) != UUID(query_id_2)
