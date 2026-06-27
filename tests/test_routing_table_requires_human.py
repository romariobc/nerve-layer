"""
Tests for routing-table.yaml requires_human field validation.

Validates that:
- All events have requires_human field
- Irreversible/high-impact events have requires_human=true
- Routing table structure is valid YAML
"""

import pytest
import yaml
from pathlib import Path


@pytest.fixture
def routing_table():
    """Load routing-table.yaml."""
    rt_path = Path(__file__).parent.parent / "routing-table.yaml"
    assert rt_path.exists(), f"routing-table.yaml not found at {rt_path}"
    with open(rt_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestRoutingTableStructure:
    """Validate routing table YAML structure."""

    def test_routing_table_exists(self):
        """routing-table.yaml exists."""
        rt_path = Path(__file__).parent.parent / "routing-table.yaml"
        assert rt_path.exists()

    def test_routing_table_is_valid_yaml(self, routing_table):
        """routing-table.yaml is valid YAML."""
        assert routing_table is not None
        assert isinstance(routing_table, dict)

    def test_routing_table_has_schema_version(self, routing_table):
        """routing-table.yaml has schema_version."""
        assert "schema_version" in routing_table
        assert routing_table["schema_version"] == "1.0.0"

    def test_routing_table_has_events_section(self, routing_table):
        """routing-table.yaml has events section."""
        assert "events" in routing_table
        assert isinstance(routing_table["events"], dict)
        assert len(routing_table["events"]) > 0


class TestRequiresHumanField:
    """Validate requires_human field across events."""

    def test_all_events_have_requires_human(self, routing_table):
        """Every event has requires_human field."""
        events = routing_table["events"]
        for event_name, config in events.items():
            assert "requires_human" in config, f"{event_name} missing requires_human"
            assert isinstance(
                config["requires_human"], bool
            ), f"{event_name} requires_human is not boolean"

    def test_brief_published_requires_human_true(self, routing_table):
        """brief.published has requires_human=true (irreversible change)."""
        events = routing_table["events"]
        assert (
            events["brief.published"]["requires_human"] is True
        ), "brief.published should have requires_human=true"

    def test_design_component_changed_requires_human_true(self, routing_table):
        """design.component.changed has requires_human=true (blocks dev)."""
        events = routing_table["events"]
        assert (
            events["design.component.changed"]["requires_human"] is True
        ), "design.component.changed should have requires_human=true"

    def test_high_impact_events_require_human(self, routing_table):
        """High-impact events that require human approval."""
        events = routing_table["events"]
        high_impact = [
            "adr.stale",
            "harness.task.blocked",
            "feature.scope.alert",
            "adapter.fidelity.report",
        ]
        for event_name in high_impact:
            assert event_name in events
            assert (
                events[event_name]["requires_human"] is True
            ), f"{event_name} should have requires_human=true"

    def test_low_impact_events_dont_require_human(self, routing_table):
        """Low-impact events don't require human approval."""
        events = routing_table["events"]
        low_impact = [
            "adr.approved",
            "adr.superseded",
            "design.token.updated",
            "harness.task.complete",
            "skill.updated",
            "query.request",
            "query.result",
        ]
        for event_name in low_impact:
            assert event_name in events
            assert (
                events[event_name]["requires_human"] is False
            ), f"{event_name} should have requires_human=false"
