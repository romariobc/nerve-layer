"""
tests/test_retry.py

Unit tests for bus/retry.py — retry logic com backoff, TTL, e reprocessamento.

Coverage:
  - Backoff calculation: exponential, linear, com/sem jitter
  - TTL expiration: should_expire(), expired_entries()
  - Retry readiness: should_retry(), ready_for_retry()
  - Next retry time calculation
  - Edge cases: max_attempts reached, TTL expiration, zero delay
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from bus.retry import (
    calculate_backoff,
    should_retry,
    should_expire,
    expired_entries,
    next_retry_time,
    ready_for_retry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def routing_table():
    return {
        "events": {
            "brief.published": {
                "retry_policy": {
                    "max_attempts": 5,
                    "backoff": "exponential",
                    "dead_letter_queue": True,
                },
                "ttl_hours": 72,
            },
            "adr.stale": {
                "retry_policy": {
                    "max_attempts": 3,
                    "backoff": "linear",
                    "dead_letter_queue": True,
                },
                "ttl_hours": 24,
            },
        }
    }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Backoff calculation
# ---------------------------------------------------------------------------

class TestCalculateBackoff:
    def test_exponential_sequence(self):
        # retry_count = 0 → 2^1 = 2s
        assert calculate_backoff(0, "exponential", jitter=False) == 2.0
        # retry_count = 1 → 2^2 = 4s
        assert calculate_backoff(1, "exponential", jitter=False) == 4.0
        # retry_count = 2 → 2^3 = 8s
        assert calculate_backoff(2, "exponential", jitter=False) == 8.0
        # retry_count = 3 → 2^4 = 16s
        assert calculate_backoff(3, "exponential", jitter=False) == 16.0

    def test_exponential_capped_at_max_delay(self):
        # retry_count = 5 → 2^6 = 64s, mas max_delay = 30s
        delay = calculate_backoff(5, "exponential", max_delay=30.0, jitter=False)
        assert delay == 30.0

    def test_linear_strategy(self):
        # Linear sempre 5s
        assert calculate_backoff(0, "linear", jitter=False) == 5.0
        assert calculate_backoff(1, "linear", jitter=False) == 5.0
        assert calculate_backoff(3, "linear", jitter=False) == 5.0

    def test_linear_capped_at_max_delay(self):
        delay = calculate_backoff(0, "linear", max_delay=3.0, jitter=False)
        assert delay == 3.0

    def test_unknown_strategy_returns_zero(self):
        delay = calculate_backoff(0, "unknown_strategy", jitter=False)
        assert delay == 0.0

    def test_jitter_varies_delay(self):
        # Com jitter, delay varia em ±20%
        delays = [calculate_backoff(0, "exponential") for _ in range(10)]
        # Base é 2s, jitter é ±0.4s, então varia de 1.6 a 2.4s
        assert all(1.6 <= d <= 2.4 for d in delays)
        # Mas nao sao todos iguais (probabilidade negligenciável)
        assert len(set(round(d, 1) for d in delays)) > 1

    def test_negative_jitter_clamped_to_zero(self):
        # Se jitter leva a delay negativo, clamp a zero
        delay = calculate_backoff(0, "linear", max_delay=0.1, jitter=True)
        assert delay >= 0.0


# ---------------------------------------------------------------------------
# TTL expiration
# ---------------------------------------------------------------------------

class TestShouldExpire:
    def test_fresh_event_not_expired(self):
        now = _now()
        queued_at = _iso(now)
        assert not should_expire(queued_at, ttl_hours=24)

    def test_event_at_ttl_boundary_is_expired(self):
        now = _now()
        queued_at = _iso(now - timedelta(hours=24))
        assert should_expire(queued_at, ttl_hours=24)

    def test_event_past_ttl_is_expired(self):
        now = _now()
        queued_at = _iso(now - timedelta(hours=48))
        assert should_expire(queued_at, ttl_hours=24)

    def test_event_just_before_ttl_not_expired(self):
        now = _now()
        queued_at = _iso(now - timedelta(hours=23, minutes=59))
        assert not should_expire(queued_at, ttl_hours=24)

    def test_naive_datetime_assumed_utc(self):
        # Sem timezone, assume UTC
        now = datetime.now()
        queued_at = (now - timedelta(hours=25)).isoformat()
        assert should_expire(queued_at, ttl_hours=24)


class TestExpiredEntries:
    def test_empty_dlq_returns_empty(self):
        assert expired_entries([]) == []

    def test_single_fresh_entry_not_expired(self):
        entries = [
            {
                "event_id": "uuid-1",
                "queued_at": _iso(_now()),
                "ttl_hours": 24,
            }
        ]
        assert expired_entries(entries) == []

    def test_single_expired_entry_returned(self):
        now = _now()
        entries = [
            {
                "event_id": "uuid-1",
                "queued_at": _iso(now - timedelta(hours=48)),
                "ttl_hours": 24,
            }
        ]
        result = expired_entries(entries)
        assert len(result) == 1
        assert result[0]["event_id"] == "uuid-1"

    def test_mixed_entries_only_expired_returned(self):
        now = _now()
        entries = [
            {"event_id": "uuid-1", "queued_at": _iso(now), "ttl_hours": 24},
            {"event_id": "uuid-2", "queued_at": _iso(now - timedelta(hours=48)), "ttl_hours": 24},
            {"event_id": "uuid-3", "queued_at": _iso(now - timedelta(hours=12)), "ttl_hours": 24},
        ]
        result = expired_entries(entries)
        assert len(result) == 1
        assert result[0]["event_id"] == "uuid-2"


# ---------------------------------------------------------------------------
# Retry eligibility
# ---------------------------------------------------------------------------

class TestShouldRetry:
    def test_within_max_attempts_can_retry(self):
        assert should_retry(0, max_attempts=5)
        assert should_retry(2, max_attempts=5)
        assert should_retry(4, max_attempts=5)

    def test_at_max_attempts_cannot_retry(self):
        assert not should_retry(5, max_attempts=5)

    def test_beyond_max_attempts_cannot_retry(self):
        assert not should_retry(6, max_attempts=5)

    def test_zero_max_attempts_never_retries(self):
        assert not should_retry(0, max_attempts=0)


class TestReadyForRetry:
    def test_ready_if_delay_elapsed_and_not_expired(self, routing_table):
        now = _now()
        # Queued 3 segundos atrás, exponential retry 0 = 2s, entao ja passou
        queued_at = _iso(now - timedelta(seconds=3))
        entry = {
            "event": {"name": "brief.published"},
            "retry_count": 0,
            "queued_at": queued_at,
            "ttl_hours": 72,
        }
        assert ready_for_retry(entry, routing_table, now=now)

    def test_not_ready_if_delay_not_elapsed(self, routing_table):
        now = _now()
        # Queued 1 segundo atras, exponential retry 0 = 2s, nao passou ainda
        queued_at = _iso(now - timedelta(seconds=1))
        entry = {
            "event": {"name": "brief.published"},
            "retry_count": 0,
            "queued_at": queued_at,
            "ttl_hours": 72,
        }
        assert not ready_for_retry(entry, routing_table, now=now)

    def test_not_ready_if_expired(self, routing_table):
        now = _now()
        queued_at = _iso(now - timedelta(hours=73))
        entry = {
            "event": {"name": "brief.published"},
            "retry_count": 0,
            "queued_at": queued_at,
            "ttl_hours": 72,
        }
        assert not ready_for_retry(entry, routing_table, now=now)

    def test_not_ready_if_max_attempts_reached(self, routing_table):
        now = _now()
        queued_at = _iso(now - timedelta(seconds=100))  # Bastante tempo passou
        entry = {
            "event": {"name": "adr.stale"},
            "retry_count": 3,  # max_attempts = 3
            "queued_at": queued_at,
            "ttl_hours": 24,
        }
        assert not ready_for_retry(entry, routing_table, now=now)


# ---------------------------------------------------------------------------
# Next retry time
# ---------------------------------------------------------------------------

class TestNextRetryTime:
    def test_exponential_with_retry_count(self, routing_table):
        now = _now()
        queued_at = _iso(now)
        entry = {
            "event": {"name": "brief.published"},
            "retry_count": 1,  # 2^(1+1) = 4s
            "queued_at": queued_at,
            "ttl_hours": 72,
        }
        next_time = next_retry_time(entry, routing_table)
        assert next_time is not None
        # Deve ser ~4s no futuro (+-jitter)
        delta = (next_time - now).total_seconds()
        assert 3 < delta < 5

    def test_linear_strategy(self, routing_table):
        now = _now()
        queued_at = _iso(now)
        entry = {
            "event": {"name": "adr.stale"},
            "retry_count": 0,
            "queued_at": queued_at,
            "ttl_hours": 24,
        }
        next_time = next_retry_time(entry, routing_table)
        assert next_time is not None
        # Linear = 5s
        delta = (next_time - now).total_seconds()
        assert 4 < delta < 6

    def test_none_if_max_attempts_reached(self, routing_table):
        now = _now()
        queued_at = _iso(now)
        entry = {
            "event": {"name": "adr.stale"},
            "retry_count": 3,  # max_attempts = 3
            "queued_at": queued_at,
            "ttl_hours": 24,
        }
        next_time = next_retry_time(entry, routing_table)
        assert next_time is None

    def test_none_if_event_unknown(self, routing_table):
        entry = {
            "event": {"name": "unknown.event"},
            "retry_count": 0,
            "queued_at": _iso(_now()),
        }
        next_time = next_retry_time(entry, routing_table)
        assert next_time is None
