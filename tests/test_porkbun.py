import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DB_PATH", "./data/test-domains.db")
os.environ["PORKBUN_ENABLED"] = "true"
os.environ["PORKBUN_API_KEY"] = "pk1_test"
os.environ["PORKBUN_SECRET_API_KEY"] = "sk1_test"
os.environ["PORKBUN_CHECK_MIN_INTERVAL"] = "0"

from app.providers import porkbun
from app.providers.base import Inconclusive, ProviderError, RateLimited


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        return self.response


class PorkbunTest(unittest.TestCase):
    def setUp(self):
        porkbun.PORKBUN_ENABLED = True
        porkbun.PORKBUN_API_KEY = "pk1_test"
        porkbun.PORKBUN_SECRET_API_KEY = "sk1_test"
        porkbun.PORKBUN_CHECK_MIN_INTERVAL = 0

    def test_check_available(self):
        session = FakeSession(FakeResponse(200, {
            "status": "SUCCESS",
            "response": {"avail": "yes", "type": "registration",
                         "price": "11.06", "premium": "no"},
            "limits": {"TTL": 10},
        }))
        info = porkbun.check("ornek.com", session=session)
        self.assertTrue(info["available"])
        self.assertEqual(info["price_cents"], 1106)
        self.assertEqual(info["price_usd"], 11.06)
        self.assertFalse(info["premium"])
        self.assertIn("/domain/checkDomain/ornek.com", session.calls[0][0])
        # credentials must be in the body
        self.assertEqual(session.calls[0][1]["apikey"], "pk1_test")

    def test_check_taken(self):
        session = FakeSession(FakeResponse(200, {
            "status": "SUCCESS",
            "response": {"avail": "no", "price": "11.06"},
        }))
        self.assertFalse(porkbun.check("ornek.com", session=session)["available"])

    def test_error_status_raises(self):
        session = FakeSession(FakeResponse(200, {"status": "ERROR", "message": "Invalid API key"}))
        with self.assertRaises(ProviderError):
            porkbun.check("ornek.com", session=session)

    def test_rate_limit_message_raises_ratelimited(self):
        session = FakeSession(FakeResponse(200, {"status": "ERROR",
                                                 "message": "Rate limit exceeded"}))
        with self.assertRaises(RateLimited):
            porkbun.check("ornek.com", session=session)

    def test_http_429_raises_ratelimited(self):
        with self.assertRaises(RateLimited):
            porkbun.check("ornek.com", session=FakeSession(FakeResponse(429)))

    def test_http_500_is_inconclusive(self):
        with self.assertRaises(Inconclusive):
            porkbun.check("ornek.com", session=FakeSession(FakeResponse(502)))

    def test_register_dry_run_payload(self):
        session = FakeSession(FakeResponse(200, {"status": "SUCCESS", "dryRun": True,
                                                 "wouldSucceed": True, "sufficientFunds": True}))
        porkbun.register("ornek.com", 1106, dry_run=True, session=session)
        url, body = session.calls[0]
        self.assertIn("/domain/create/ornek.com", url)
        self.assertEqual(body["cost"], 1106)
        self.assertEqual(body["agreeToTerms"], "yes")
        self.assertTrue(body["dryRun"])

    def test_register_live_payload_has_no_dry_run_flag(self):
        session = FakeSession(FakeResponse(200, {"status": "SUCCESS", "domain": "ornek.com",
                                                 "orderId": 1, "cost": 1106}))
        porkbun.register("ornek.com", 1106, dry_run=False, session=session)
        self.assertNotIn("dryRun", session.calls[0][1])

    def test_owns_verification(self):
        session = FakeSession(FakeResponse(200, {"status": "SUCCESS",
                                                 "domains": [{"domain": "ORNEK.COM"}]}))
        owned, record = porkbun.owns("ornek.com", session=session)
        self.assertTrue(owned)
        self.assertIsNotNone(record)


if __name__ == "__main__":
    unittest.main()
