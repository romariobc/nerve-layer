"""
Tests for mcp/figma_connector.py

Validates FigmaConnector:
- on_component_changed() emits design.component.changed events
- on_variable_changed() emits design.component.changed for tokens
- Payload mapping from Figma webhook format to Nerve event schema
- Optional fields handled correctly
- Integration with EventBus mock
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock

from mcp.figma_connector import FigmaConnector


@pytest.fixture
def mock_event_bus():
    bus = Mock()
    bus.emit = Mock(return_value="test-event-id-123")
    return bus


@pytest.fixture
def figma_connector(mock_event_bus):
    return FigmaConnector(event_bus_module=mock_event_bus)


class TestFigmaConnectorComponentChanged:
    def test_component_changed_emits_event(self, figma_connector, mock_event_bus):
        payload = {
            "component_id": "comp-123",
            "component_name": "Button/Primary",
            "project_slug": "my-project",
            "change_type": "modified",
            "changed_at": "2026-06-27T10:00:00Z",
        }
        event_id = figma_connector.on_component_changed(payload)
        assert event_id == "test-event-id-123"
        mock_event_bus.emit.assert_called_once()

    def test_component_changed_payload_structure(self, figma_connector, mock_event_bus):
        payload = {
            "component_id": "comp-456",
            "component_name": "Input/Text",
            "project_slug": "another-project",
            "change_type": "created",
            "changed_at": "2026-06-27T11:00:00Z",
        }
        figma_connector.on_component_changed(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert emitted_event["name"] == "design.component.changed"
        assert emitted_event["source"] == "figma"
        assert emitted_event["payload"]["component_id"] == "comp-456"
        assert emitted_event["payload"]["component_name"] == "Input/Text"

    def test_component_changed_with_affected_tokens(self, figma_connector, mock_event_bus):
        payload = {
            "component_id": "comp-789",
            "component_name": "Card/Default",
            "project_slug": "ui-kit",
            "change_type": "modified",
            "affected_tokens": ["color/primary", "spacing/md"],
        }
        figma_connector.on_component_changed(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert emitted_event["payload"]["affected_tokens"] == ["color/primary", "spacing/md"]

    def test_component_changed_with_figma_url(self, figma_connector, mock_event_bus):
        payload = {
            "component_id": "comp-101",
            "component_name": "Badge/Success",
            "project_slug": "design-system",
            "change_type": "modified",
            "figma_url": "https://figma.com/file/abc123/components?node-id=comp-101",
        }
        figma_connector.on_component_changed(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert "figma_url" in emitted_event["payload"]

    def test_component_changed_with_breaking_flag(self, figma_connector, mock_event_bus):
        payload = {
            "component_id": "comp-202",
            "component_name": "Modal/Dialog",
            "project_slug": "ui-kit",
            "change_type": "modified",
            "breaking": True,
        }
        figma_connector.on_component_changed(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert emitted_event["payload"]["breaking"] is True

    def test_component_changed_deleted(self, figma_connector, mock_event_bus):
        payload = {
            "component_id": "comp-old",
            "component_name": "OldComponent/Legacy",
            "project_slug": "ui-kit",
            "change_type": "deleted",
        }
        figma_connector.on_component_changed(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert emitted_event["payload"]["change_type"] == "deleted"

    def test_component_changed_renamed(self, figma_connector, mock_event_bus):
        payload = {
            "component_id": "comp-renamed",
            "component_name": "Button/Secondary",
            "project_slug": "ui-kit",
            "change_type": "renamed",
        }
        figma_connector.on_component_changed(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert emitted_event["payload"]["change_type"] == "renamed"


class TestFigmaConnectorVariableChanged:
    def test_variable_changed_emits_event(self, figma_connector, mock_event_bus):
        payload = {
            "variable_id": "var-color-primary",
            "variable_name": "color/primary",
            "project_slug": "design-system",
            "change_type": "modified",
        }
        event_id = figma_connector.on_variable_changed(payload)
        assert event_id == "test-event-id-123"
        mock_event_bus.emit.assert_called_once()

    def test_variable_changed_payload_structure(self, figma_connector, mock_event_bus):
        payload = {
            "variable_id": "var-spacing-lg",
            "variable_name": "spacing/large",
            "project_slug": "tokens",
            "change_type": "modified",
            "changed_at": "2026-06-27T12:00:00Z",
        }
        figma_connector.on_variable_changed(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert emitted_event["name"] == "design.component.changed"
        assert emitted_event["source"] == "figma"

    def test_variable_changed_with_figma_url(self, figma_connector, mock_event_bus):
        payload = {
            "variable_id": "var-color-secondary",
            "variable_name": "color/secondary",
            "project_slug": "design-system",
            "change_type": "modified",
            "figma_url": "https://figma.com/file/xyz/variables?var=color%2Fsecondary",
        }
        figma_connector.on_variable_changed(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert "figma_url" in emitted_event["payload"]

    def test_variable_changed_with_breaking_flag(self, figma_connector, mock_event_bus):
        payload = {
            "variable_id": "var-critical",
            "variable_name": "color/danger",
            "project_slug": "design-system",
            "change_type": "modified",
            "breaking": True,
        }
        figma_connector.on_variable_changed(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert emitted_event["payload"]["breaking"] is True


class TestFigmaConnectorIntegration:
    def test_connector_initializes_with_event_bus(self, mock_event_bus):
        connector = FigmaConnector(event_bus_module=mock_event_bus)
        assert connector.event_bus is mock_event_bus

    def test_connector_initializes_without_event_bus(self):
        connector = FigmaConnector()
        assert connector.event_bus is not None

    def test_multiple_events_sequence(self, figma_connector, mock_event_bus):
        payload1 = {
            "component_id": "comp-1",
            "component_name": "Button",
            "project_slug": "ui",
            "change_type": "modified",
        }
        payload2 = {
            "component_id": "comp-2",
            "component_name": "Badge",
            "project_slug": "ui",
            "change_type": "modified",
        }
        figma_connector.on_component_changed(payload1)
        figma_connector.on_component_changed(payload2)
        assert mock_event_bus.emit.call_count == 2
