import time
import unittest

from infra import retry_call, tick_round
from regime import RegimeClassifier
from structure import nearest_target, room_to_target


class TestInfra(unittest.TestCase):
    def test_retry_retries_only_requested_exceptions(self):
        calls = {"n": 0}

        class TemporaryError(Exception):
            pass

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise TemporaryError("temporary")
            return "ok"

        result = retry_call(
            flaky,
            attempts=3,
            base_delay=0,
            retryable_exceptions=(TemporaryError,),
        )
        self.assertEqual(result, "ok")
        self.assertEqual(calls["n"], 3)

    def test_retry_rejects_invalid_attempts(self):
        with self.assertRaises(ValueError):
            retry_call(lambda: None, attempts=0)

    def test_tick_round_uses_half_up(self):
        self.assertEqual(tick_round(1.025, 0.05), 1.05)
        self.assertEqual(tick_round(1.024, 0.05), 1.0)
        self.assertEqual(tick_round(0, 0.05), 0.0)


class TestStructure(unittest.TestCase):
    def test_nearest_bullish_target(self):
        target = nearest_target(
            100,
            "BUY",
            cpr={"r1": 112, "r2": 125},
            prev_high=110,
            call_walls=[108],
            margin=2,
        )
        self.assertEqual(target, (108.0, "CALL-WALL"))

    def test_room_matches_target(self):
        room = room_to_target(
            100,
            "SELL",
            cpr={"s1": 92},
            prev_low=95,
            put_walls=[94],
            margin=2,
        )
        self.assertEqual(room, 5.0)


class TestRegime(unittest.TestCase):
    def test_expiry_takes_priority(self):
        result = RegimeClassifier({}).classify(
            day_quality="TRENDING",
            vix=18,
            is_expiry_day=True,
            direction_hint="bullish",
        )
        self.assertEqual(result.regime, "EXPIRY")
        self.assertFalse(result.sit_out)

    def test_unclear_stands_down_by_default(self):
        result = RegimeClassifier({}).classify(day_quality="UNKNOWN")
        self.assertEqual(result.regime, "UNCLEAR")
        self.assertTrue(result.sit_out)


if __name__ == "__main__":
    unittest.main()
