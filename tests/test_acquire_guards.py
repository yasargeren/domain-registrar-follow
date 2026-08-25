"""The safety gates are the most important code in this project: test them."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_TMP = tempfile.mkdtemp(prefix="dfr-test-")
os.environ["DB_PATH"] = str(Path(_TMP) / "test.db")
os.environ["KILL_SWITCH_FILE"] = str(Path(_TMP) / "STOP")
os.environ["ACQUIRE_ALLOWLIST"] = "ornek1.com.tr,ornek2.com.tr,ornek.com"
os.environ["AUTO_REGISTER"] = "false"
os.environ["MAX_REGISTRATION_COST_USD"] = "50"
os.environ["TELEGRAM_ENABLED"] = "false"
os.environ["EMAIL_ENABLED"] = "false"
os.environ["WEBHOOK_ENABLED"] = "false"

from app import acquire, config, db


class GateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init()

    def tearDown(self):
        if config.KILL_SWITCH_FILE.exists():
            config.KILL_SWITCH_FILE.unlink()
        config.AUTO_REGISTER = False

    def test_g1_allowlist_blocks_foreign_domain(self):
        with self.assertRaises(acquire.Blocked) as ctx:
            acquire.preflight("example.com", live=False)
        self.assertIn("G1", str(ctx.exception))

    def test_g2_kill_switch_blocks(self):
        config.KILL_SWITCH_FILE.write_text("stop")
        with self.assertRaises(acquire.Blocked) as ctx:
            acquire.preflight("ornek.com", live=False)
        self.assertIn("G2", str(ctx.exception))

    def test_g3_auto_register_false_blocks_live(self):
        with self.assertRaises(acquire.Blocked) as ctx:
            acquire.preflight("ornek.com", live=True)
        self.assertIn("G3", str(ctx.exception))

    def test_dry_run_allowed_while_auto_register_false(self):
        self.assertEqual(acquire.preflight("ornek.com", live=False), "ornek.com")

    def test_g7_price_cap(self):
        with self.assertRaises(acquire.Blocked) as ctx:
            acquire._price_gate({"price_usd": 999.0, "premium": True}, "ornek.com")
        self.assertIn("G7", str(ctx.exception))

    def test_g7_missing_price_blocks(self):
        with self.assertRaises(acquire.Blocked):
            acquire._price_gate({"price_usd": None}, "ornek.com")

    def test_g7_allows_normal_price(self):
        self.assertEqual(acquire._price_gate({"price_usd": 11.06}, "ornek.com"), 11.06)

    def test_blocked_attempt_is_recorded(self):
        acquire.try_acquire("example.com", live=True)
        rows = db.last_attempts("example.com", 5)
        self.assertTrue(rows)
        self.assertEqual(rows[0]["outcome"], "blocked")

    def test_tr_domain_requires_manual_registration(self):
        config.AUTO_REGISTER = True
        result = acquire.try_acquire("ornek1.com.tr", live=True)
        self.assertFalse(result["ok"])
        rows = db.last_attempts("ornek1.com.tr", 5)
        self.assertEqual(rows[0]["outcome"], "blocked")
        self.assertIn("MANUEL", rows[0]["detail"].upper())


if __name__ == "__main__":
    unittest.main()
