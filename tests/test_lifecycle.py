import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DB_PATH", "./data/test-domains.db")

from app import lifecycle
from app.providers.base import LookupResult

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def res(**kw):
    kw.setdefault("domain", "ornek.com")
    kw.setdefault("available", False)
    return LookupResult(**kw)


class ClassifyTest(unittest.TestCase):
    def test_available(self):
        self.assertEqual(lifecycle.classify(res(available=True), NOW), lifecycle.AVAILABLE)

    def test_pending_delete_wins(self):
        r = res(statuses=["clientTransferProhibited", "pendingDelete"],
                expiration=(NOW + timedelta(days=200)).isoformat())
        self.assertEqual(lifecycle.classify(r, NOW), lifecycle.PENDING_DELETE)

    def test_redemption(self):
        r = res(statuses=["redemptionPeriod"])
        self.assertEqual(lifecycle.classify(r, NOW), lifecycle.REDEMPTION)

    def test_status_normalization(self):
        r = res(statuses=["redemption period"])
        self.assertEqual(lifecycle.classify(r, NOW), lifecycle.REDEMPTION)

    def test_expired_grace(self):
        r = res(statuses=["ok"], expiration=(NOW - timedelta(days=3)).isoformat())
        self.assertEqual(lifecycle.classify(r, NOW), lifecycle.EXPIRED_GRACE)

    def test_expiring_soon(self):
        r = res(statuses=["ok"], expiration=(NOW + timedelta(days=10)).isoformat())
        self.assertEqual(lifecycle.classify(r, NOW), lifecycle.EXPIRING)

    def test_active(self):
        r = res(statuses=["ok"], expiration=(NOW + timedelta(days=300)).isoformat())
        self.assertEqual(lifecycle.classify(r, NOW), lifecycle.ACTIVE)

    def test_unknown_without_any_signal(self):
        self.assertEqual(lifecycle.classify(res(), NOW), lifecycle.UNKNOWN)

    def test_z_suffix_expiration(self):
        r = res(statuses=["ok"], expiration="2026-09-01T10:00:00Z")
        self.assertEqual(lifecycle.classify(r, NOW), lifecycle.EXPIRING)


class IntervalTest(unittest.TestCase):
    def test_critical_states_poll_fastest(self):
        for state in lifecycle.CRITICAL_STATES:
            self.assertLessEqual(lifecycle.interval_for(state),
                                 lifecycle.interval_for(lifecycle.EXPIRING))

    def test_active_is_slowest(self):
        self.assertGreaterEqual(lifecycle.interval_for(lifecycle.ACTIVE),
                                lifecycle.interval_for(lifecycle.EXPIRING))


class EscalationTest(unittest.TestCase):
    def test_escalation_detected(self):
        self.assertTrue(lifecycle.is_escalation(lifecycle.ACTIVE, lifecycle.REDEMPTION))
        self.assertTrue(lifecycle.is_escalation(lifecycle.PENDING_DELETE, lifecycle.AVAILABLE))

    def test_de_escalation_not_flagged(self):
        self.assertFalse(lifecycle.is_escalation(lifecycle.REDEMPTION, lifecycle.ACTIVE))


class DropWindowTest(unittest.TestCase):
    def test_com_estimate(self):
        window = lifecycle.estimated_drop_window("2026-01-01T00:00:00Z", "com")
        self.assertEqual(window["drop_expected"][:10], "2026-03-22")  # 1 Oca + 45 + 30 + 5 gun

    def test_no_estimate_for_tr(self):
        self.assertIsNone(lifecycle.estimated_drop_window("2026-01-01T00:00:00Z", "com.tr"))


if __name__ == "__main__":
    unittest.main()
