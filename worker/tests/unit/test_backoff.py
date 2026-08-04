"""
Unit Tests for Exponential Backoff Delay Calculation.

Tests the compute_backoff_delay function from the worker's main module,
verifying exponential growth, jitter bounds, and max-delay capping.
"""

import pytest
from unittest.mock import patch

# Import the function under test
from app.main import compute_backoff_delay


class TestComputeBackoffDelay:
    """Test suite for compute_backoff_delay(attempts, base_delay, max_delay)."""

    # ── Exponential growth ───────────────────────────────────

    def test_first_attempt_returns_base_delay_range(self):
        """Attempt 1 → delay ∈ [base, base * 1.5] (base + up to 50% jitter)."""
        base = 2.0
        delay = compute_backoff_delay(1, base_delay=base)
        # base * 2^(1-1) = 2.0, jitter ∈ [0, 1.0]
        assert base <= delay <= base * 1.5

    def test_second_attempt_doubles(self):
        """Attempt 2 → exponential part = base * 2^1 = 4.0."""
        base = 2.0
        delay = compute_backoff_delay(2, base_delay=base)
        exponential = base * (2 ** 1)  # 4.0
        assert exponential <= delay <= exponential * 1.5

    def test_third_attempt_quadruples(self):
        """Attempt 3 → exponential part = base * 2^2 = 8.0."""
        base = 2.0
        delay = compute_backoff_delay(3, base_delay=base)
        exponential = base * (2 ** 2)  # 8.0
        assert exponential <= delay <= exponential * 1.5

    def test_delay_increases_monotonically_without_jitter(self):
        """With jitter mocked to 0, delays should strictly increase."""
        with patch("app.main.random.uniform", return_value=0):
            delays = [compute_backoff_delay(a) for a in range(1, 6)]
        for i in range(len(delays) - 1):
            assert delays[i] < delays[i + 1], (
                f"Delay at attempt {i+1} ({delays[i]}) should be < "
                f"delay at attempt {i+2} ({delays[i+1]})"
            )

    # ── Max delay cap ────────────────────────────────────────

    def test_max_delay_is_respected(self):
        """Even at very high attempt counts, delay should never exceed max_delay * 1.5."""
        max_d = 100.0
        delay = compute_backoff_delay(20, base_delay=2.0, max_delay=max_d)
        # Jitter is up to 50% of the capped delay
        assert delay <= max_d * 1.5

    def test_max_delay_caps_exponential_part(self):
        """With jitter=0, delay at high attempts should equal max_delay exactly."""
        max_d = 60.0
        with patch("app.main.random.uniform", return_value=0):
            delay = compute_backoff_delay(50, base_delay=2.0, max_delay=max_d)
        assert delay == max_d

    # ── Jitter behaviour ────────────────────────────────────

    def test_jitter_adds_positive_value(self):
        """Jitter should make the delay ≥ the pure exponential component."""
        base = 2.0
        exponential = base * (2 ** 0)  # attempt=1 → 2.0
        delay = compute_backoff_delay(1, base_delay=base)
        assert delay >= exponential

    def test_jitter_upper_bound(self):
        """Jitter should be at most 50% of the exponential component."""
        base = 2.0
        for attempt in range(1, 10):
            exponential = min(base * (2 ** (attempt - 1)), 3600.0)
            delay = compute_backoff_delay(attempt, base_delay=base)
            assert delay <= exponential * 1.5 + 0.01  # small float tolerance

    # ── Return type ─────────────────────────────────────────

    def test_returns_float(self):
        """Result should always be a float."""
        result = compute_backoff_delay(1)
        assert isinstance(result, float)

    def test_result_is_rounded_to_two_decimals(self):
        """Result should be rounded to 2 decimal places."""
        result = compute_backoff_delay(3)
        assert result == round(result, 2)

    # ── Edge cases ──────────────────────────────────────────

    def test_custom_base_delay(self):
        """Custom base_delay should be used as the foundation."""
        with patch("app.main.random.uniform", return_value=0):
            delay = compute_backoff_delay(1, base_delay=10.0)
        assert delay == 10.0

    def test_large_attempt_number(self):
        """Very large attempt numbers should not raise errors or overflow."""
        delay = compute_backoff_delay(100, base_delay=2.0, max_delay=3600.0)
        assert delay <= 3600.0 * 1.5
        assert delay > 0
