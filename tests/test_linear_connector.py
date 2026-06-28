"""
Tests for mcp/linear_connector.py

Validates LinearConnector:
- on_issue_status_changed() emits project.status.changed events
- Payload mapping from Linear webhook format to Nerve event schema
- Optional fields handled correctly
- query_project_status() returns project state without emitting
- Integration with EventBus mock
- API key handling
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock

from mcp.linear_connector import LinearConnector


@pytest.fixture
def mock_event_bus():
    bus = Mock()
    bus.emit = Mock(return_value="linear-event-id-456")
    return bus


@pytest.fixture
def linear_connector(mock_event_bus):
    return LinearConnector(event_bus_module=mock_event_bus, api_key="test-api-key")


class TestLinearConnectorStatusChanged:
    def test_status_changed_emits_event(self, linear_connector, mock_event_bus):
        payload = {
            "project_id": "proj-123",
            "project_name": "Marketing Campaign",
            "issue_count": 42,
            "status": "in_progress",
        }
        event_id = linear_connector.on_issue_status_changed(payload)
        assert event_id == "linear-event-id-456"
        mock_event_bus.emit.assert_called_once()

    def test_status_changed_payload_structure(self, linear_connector, mock_event_bus):
        payload = {
            "project_id": "proj-456",
            "project_name": "Product Roadmap",
            "issue_count": 15,
            "status": "todo",
        }
        linear_connector.on_issue_status_changed(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert emitted_event["name"] == "project.status.changed"
        assert emitted_event["source"] == "linear"
        assert emitted_event["payload"]["project_id"] == "proj-456"
        assert emitted_event["payload"]["project_name"] == "Product Roadmap"
        assert emitted_event["payload"]["issue_count"] == 15
        assert emitted_event["payload"]["status"] == "todo"

    def test_status_changed_all_status_types(self, linear_connector, mock_event_bus):
        statuses = ["backlog", "todo", "in_progress", "in_review", "done"]
        for status in statuses:
            payload = {
                "project_id": f"proj-{status}",
                "project_name": f"Project {status}",
                "issue_count": 10,
                "status": status,
            }
            linear_connector.on_issue_status_changed(payload)
            emitted_event = mock_event_bus.emit.call_args[0][0]
            assert emitted_event["payload"]["status"] == status

    def test_status_changed_with_team_id(self, linear_connector, mock_event_bus):
        payload = {
            "project_id": "proj-789",
            "project_name": "Team Project",
            "issue_count": 5,
            "status": "done",
            "team_id": "team-123",
        }
        linear_connector.on_issue_status_changed(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert "team_id" in emitted_event["payload"]
        assert emitted_event["payload"]["team_id"] == "team-123"

    def test_status_changed_with_url(self, linear_connector, mock_event_bus):
        payload = {
            "project_id": "proj-101",
            "project_name": "API Refactor",
            "issue_count": 8,
            "status": "in_progress",
            "url": "https://linear.app/workspace/project/proj-101",
        }
        linear_connector.on_issue_status_changed(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert "url" in emitted_event["payload"]
        assert emitted_event["payload"]["url"] == "https://linear.app/workspace/project/proj-101"

    def test_status_changed_with_updated_at(self, linear_connector, mock_event_bus):
        payload = {
            "project_id": "proj-202",
            "project_name": "Maintenance",
            "issue_count": 20,
            "status": "in_review",
            "updated_at": "2026-06-27T14:00:00Z",
        }
        linear_connector.on_issue_status_changed(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert emitted_event["payload"]["updated_at"] == "2026-06-27T14:00:00Z"

    def test_status_changed_auto_timestamp(self, linear_connector, mock_event_bus):
        payload = {
            "project_id": "proj-303",
            "project_name": "Documentation",
            "issue_count": 3,
            "status": "todo",
        }
        linear_connector.on_issue_status_changed(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert "updated_at" in emitted_event["payload"]
        # Verify it's a valid ISO format timestamp
        assert "T" in emitted_event["payload"]["updated_at"]

    def test_status_changed_zero_issues(self, linear_connector, mock_event_bus):
        payload = {
            "project_id": "proj-new",
            "project_name": "New Project",
            "issue_count": 0,
            "status": "backlog",
        }
        linear_connector.on_issue_status_changed(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert emitted_event["payload"]["issue_count"] == 0

    def test_status_changed_large_issue_count(self, linear_connector, mock_event_bus):
        payload = {
            "project_id": "proj-large",
            "project_name": "Huge Project",
            "issue_count": 1000,
            "status": "in_progress",
        }
        linear_connector.on_issue_status_changed(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert emitted_event["payload"]["issue_count"] == 1000


class TestLinearConnectorQueryProjectStatus:
    def test_query_project_status_returns_dict(self, linear_connector):
        result = linear_connector.query_project_status("proj-query-1")
        assert isinstance(result, dict)

    def test_query_project_status_contains_required_fields(self, linear_connector):
        result = linear_connector.query_project_status("proj-query-2")
        assert "project_id" in result
        assert "project_name" in result
        assert "issue_count" in result
        assert "status" in result
        assert "url" in result

    def test_query_project_status_with_different_project_ids(self, linear_connector):
        proj_id_1 = "proj-abc-123"
        proj_id_2 = "proj-xyz-789"
        
        result1 = linear_connector.query_project_status(proj_id_1)
        result2 = linear_connector.query_project_status(proj_id_2)
        
        assert result1["project_id"] == proj_id_1
        assert result2["project_id"] == proj_id_2


class TestLinearConnectorIntegration:
    def test_connector_initializes_with_event_bus(self, mock_event_bus):
        connector = LinearConnector(event_bus_module=mock_event_bus, api_key="key123")
        assert connector.event_bus is mock_event_bus
        assert connector.api_key == "key123"

    def test_connector_initializes_without_event_bus(self):
        connector = LinearConnector(api_key="key456")
        assert connector.event_bus is not None
        assert connector.api_key == "key456"

    def test_connector_initializes_with_default_api_key(self):
        connector = LinearConnector()
        assert connector.api_key == ""
