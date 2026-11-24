"""The Anthropic spend counter: prices, token accounting, and how it is shown."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.services.scan_view import scan_summary
from app.usage import usage_row
from shared_models.pricing import CACHE_READ_FACTOR, CACHE_WRITE_FACTOR, cost_usd, price_for

T0 = datetime(2026, 11, 18, 18, 0, tzinfo=UTC)


class TestPricing:
    def test_haiku_cost_from_tokens(self) -> None:
        # $1 / MTok in, $5 / MTok out: 10k in + 2k out = 0.01 + 0.01
        assert cost_usd("claude-haiku-4-5", input_tokens=10_000, output_tokens=2_000) == pytest.approx(0.02)

    def test_cached_tokens_are_priced_apart_from_input(self) -> None:
        c = cost_usd("claude-haiku-4-5", input_tokens=1_000_000, cache_read_tokens=1_000_000, cache_write_tokens=1_000_000)
        assert c == pytest.approx(1.0 + 1.0 * CACHE_READ_FACTOR + 1.0 * CACHE_WRITE_FACTOR)

    def test_dated_snapshots_use_the_family_price(self) -> None:
        assert price_for("claude-haiku-4-5-20251001")[:2] == (1.0, 5.0)
        assert price_for("claude-sonnet-4-5-20250929")[:2] == (3.0, 15.0)

    def test_unknown_model_is_priced_as_haiku_but_flagged(self) -> None:
        p_in, p_out, known = price_for("claude-something-new")
        assert (p_in, p_out, known) == (1.0, 5.0, False)

    def test_override_wins(self) -> None:
        assert cost_usd("claude-haiku-4-5", input_tokens=1_000_000, override=(2.0, 10.0)) == pytest.approx(2.0)
        # a zero override means "use the table"
        assert cost_usd("claude-haiku-4-5", input_tokens=1_000_000, override=(0.0, 0.0)) == pytest.approx(1.0)

    def test_zero_tokens_cost_nothing(self) -> None:
        assert cost_usd("claude-haiku-4-5") == 0.0


class TestUsageRow:
    def test_row_from_a_response_usage(self) -> None:
        usage = SimpleNamespace(input_tokens=12_000, output_tokens=800, cache_read_input_tokens=5_000,
                                cache_creation_input_tokens=0)
        row = usage_row(usage, model="claude-haiku-4-5", purpose="extract", label="albo:abc")
        assert row["input_tokens"] == 12_000 and row["output_tokens"] == 800
        assert row["cache_read_tokens"] == 5_000 and row["cache_write_tokens"] == 0
        # 12000*1e-6 + 800*5e-6 + 5000*1e-6*0.1 = 0.012 + 0.004 + 0.0005
        assert row["cost_usd"] == pytest.approx(0.0165, abs=1e-6)
        assert row["purpose"] == "extract" and row["label"] == "albo:abc"

    def test_missing_cache_fields_count_as_zero(self) -> None:
        row = usage_row(SimpleNamespace(input_tokens=1000, output_tokens=0), model="claude-haiku-4-5",
                        purpose="links", label=None)
        assert row["cache_read_tokens"] == 0 and row["label"] is None


class TestScanCosts:
    def test_run_and_comune_costs_are_shown(self) -> None:
        run = SimpleNamespace(id="r", region="Puglia", status="done", started_at=T0, ended_at=T0 + timedelta(seconds=60),
                              heartbeat_at=T0, sample_limit=None, error=None, claude_status="ok", claude_error=None)

        def item(i, ente):
            return SimpleNamespace(id=i, ente=ente, status="done", started_at=T0, ended_at=T0 + timedelta(seconds=30),
                                   pages_read=1, pages_skipped=0, claude_calls=1, claude_errors=0, records_found=0,
                                   deepest=1, stopped_by=None, error=None)

        s = scan_summary(run, [item("a", "A"), item("b", "B")], T0 + timedelta(seconds=90),
                         costs={"a": 0.0123456}, run_cost=0.05)
        assert s["cost_usd"] == 0.05
        by = {i["ente"]: i["cost_usd"] for i in s["items"]}
        assert by == {"A": 0.0123, "B": 0.0}  # a comune without calls costs nothing

    def test_without_cost_data_the_fields_are_none(self) -> None:
        run = SimpleNamespace(id="r", region=None, status="running", started_at=T0, ended_at=None, heartbeat_at=T0,
                              sample_limit=None, error=None, claude_status="unused", claude_error=None)
        s = scan_summary(run, [], T0 + timedelta(seconds=5))
        assert s["cost_usd"] is None
