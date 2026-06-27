import json
import uuid
from pathlib import Path
import pytest
import yaml
from validator import validate_event, validate_payload_only, ValidationError

_ROOT = Path(__file__).parent.parent
_FIXTURES = Path(__file__).parent / "fixtures"


def _base_event(**overrides):
    event = {
        "id": str(uuid.uuid4()),
        "name": "brief.published",
        "source": "project-studio",
        "timestamp": "2026-06-27T10:00:00Z",
        "payload": {
            "brief_version": "1.0.0",
            "brief_hash": "sha256:" + "a" * 64,
            "project_slug": "test-project",
            "changed_sections": ["CONTEX.md"],
            "full_reload_required": False,
        },
        "routing": {
            "subscribers": ["agent-dev-harness"],
            "requires_human": False,
            "priority": "normal",
        },
        "meta": {"schema_version": "1.0.0", "retry_count": 0},
    }
    event.update(overrides)
    return event


class TestEnvelopeValidation:
    def test_valid_event_passes(self):
        validate_event(_base_event())

    def test_missing_id_raises(self):
        e = _base_event(); del e["id"]
        with pytest.raises(ValidationError): validate_event(e)

    def test_missing_name_raises(self):
        e = _base_event(); del e["name"]
        with pytest.raises(ValidationError): validate_event(e)

    def test_missing_source_raises(self):
        e = _base_event(); del e["source"]
        with pytest.raises(ValidationError): validate_event(e)

    def test_missing_timestamp_raises(self):
        e = _base_event(); del e["timestamp"]
        with pytest.raises(ValidationError): validate_event(e)

    def test_missing_payload_raises(self):
        e = _base_event(); del e["payload"]
        with pytest.raises(ValidationError): validate_event(e)

    def test_missing_routing_raises(self):
        e = _base_event(); del e["routing"]
        with pytest.raises(ValidationError): validate_event(e)

    def test_missing_meta_raises(self):
        e = _base_event(); del e["meta"]
        with pytest.raises(ValidationError): validate_event(e)

    def test_unknown_event_name_raises(self):
        with pytest.raises(ValidationError): validate_event(_base_event(name="unknown.event"))

    def test_unknown_source_raises(self):
        with pytest.raises(ValidationError): validate_event(_base_event(source="unknown-system"))

    def test_invalid_priority_raises(self):
        e = _base_event(); e["routing"]["priority"] = "critical"
        with pytest.raises(ValidationError): validate_event(e)

    def test_additional_property_rejected(self):
        e = _base_event(); e["unexpected_field"] = "value"
        with pytest.raises(ValidationError): validate_event(e)

    def test_optional_correlation_id_accepted(self):
        e = _base_event(); e["meta"]["correlation_id"] = str(uuid.uuid4())
        validate_event(e)


class TestBriefPublished:
    def test_valid_from_fixture(self):
        data = json.loads((_FIXTURES / "brief_published_valid.json").read_text())
        validate_event(data)

    def test_missing_brief_version_raises(self):
        e = _base_event(); del e["payload"]["brief_version"]
        with pytest.raises(ValidationError): validate_event(e)

    def test_invalid_hash_format_raises(self):
        e = _base_event(); e["payload"]["brief_hash"] = "not-a-valid-hash"
        with pytest.raises(ValidationError): validate_event(e)


class TestAdrApproved:
    def _adr_event(self, **payload_overrides):
        payload = {
            "adr_id": "ADR-001",
            "adr_title": "Use PostgreSQL as primary database",
            "project_slug": "test-project",
            "approved_by": "romariobc",
            "approved_at": "2026-06-27T10:00:00Z",
            "supersedes": [],
        }
        payload.update(payload_overrides)
        return _base_event(name="adr.approved", source="project-studio", payload=payload)

    def test_valid_adr_passes(self):
        validate_event(self._adr_event())

    def test_invalid_adr_id_pattern_raises(self):
        with pytest.raises(ValidationError): validate_event(self._adr_event(adr_id="adr-1"))


class TestFeatureScopeAlert:
    def _alert_event(self, **payload_overrides):
        payload = {
            "project_slug": "test-project",
            "alert_type": "out_of_scope",
            "detected_at": "2026-06-27T10:00:00Z",
            "trigger_text": "implement payment gateway",
            "matched_rule": {"layer": "computational", "rule": "SCOPE_GUARDRAIL_001"},
        }
        payload.update(payload_overrides)
        return _base_event(name="feature.scope.alert", source="agent-dev-harness", payload=payload)

    def test_valid_computational_alert_passes(self):
        validate_event(self._alert_event())

    def test_invalid_alert_type_raises(self):
        with pytest.raises(ValidationError): validate_event(self._alert_event(alert_type="unknown_type"))


class TestHarnessTaskBlocked:
    def _blocked_event(self, **payload_overrides):
        payload = {
            "feature_id": "feat-123",
            "project_slug": "test-project",
            "domain": "checkout",
            "blocked_at": "2026-06-27T10:00:00Z",
            "blocker_type": "adr_pending",
            "reason": "ADR-002 not yet approved by Tech Lead",
        }
        payload.update(payload_overrides)
        return _base_event(name="harness.task.blocked", source="agent-dev-harness", payload=payload)

    def test_valid_blocked_event_passes(self):
        validate_event(self._blocked_event())

    def test_invalid_blocker_type_raises(self):
        with pytest.raises(ValidationError): validate_event(self._blocked_event(blocker_type="just_because"))


class TestAllEventsCovered:
    def test_every_event_name_has_payload_schema(self):
        envelope = yaml.safe_load(
            (_ROOT / "schemas" / "event.schema.yaml").read_text(encoding="utf-8")
        )
        event_names = envelope["properties"]["name"]["enum"]
        events_dir = _ROOT / "schemas" / "events"
        missing = [n for n in event_names if not (events_dir / f"{n}.yaml").exists()]
        assert not missing, f"Missing payload schemas for: {missing}"


class TestValidatePayloadOnly:
    def test_valid_payload_passes(self):
        validate_payload_only("brief.published", {
            "brief_version": "2.0.0",
            "brief_hash": "sha256:" + "f" * 64,
            "project_slug": "my-project",
            "changed_sections": ["DOMAIN.md"],
            "full_reload_required": False,
        })

    def test_invalid_payload_raises(self):
        with pytest.raises(ValidationError): validate_payload_only("brief.published", {"brief_version": "not-semver"})

    def test_unknown_event_name_raises(self):
        with pytest.raises(ValidationError): validate_payload_only("does.not.exist", {})
