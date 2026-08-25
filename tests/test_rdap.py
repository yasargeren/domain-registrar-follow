import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DB_PATH", "./data/test-domains.db")

from app.providers import rdap
from app.providers.base import Inconclusive, RateLimited

FIX = Path(__file__).parent / "fixtures"


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

    def get(self, *_args, **_kwargs):
        return self.response


class RdapTest(unittest.TestCase):
    def test_registered(self):
        payload = json.loads((FIX / "rdap_registered.json").read_text())
        result = rdap.lookup("ornek.com", session=FakeSession(FakeResponse(200, payload)))
        self.assertFalse(result.available)
        self.assertIn("redemptionPeriod", result.statuses)
        self.assertEqual(result.expiration, "2026-05-04T10:00:00Z")
        self.assertEqual(result.created, "2018-05-04T10:00:00Z")
        self.assertEqual(result.registrar, "Ornek Registrar, Inc.")
        self.assertEqual(result.nameservers, ["ns1.example.com", "ns2.example.com"])

    def test_404_means_available(self):
        result = rdap.lookup("ornek.com", session=FakeSession(FakeResponse(404)))
        self.assertTrue(result.available)

    def test_429_raises(self):
        with self.assertRaises(RateLimited):
            rdap.lookup("ornek.com", session=FakeSession(FakeResponse(429)))

    def test_500_is_inconclusive(self):
        with self.assertRaises(Inconclusive):
            rdap.lookup("ornek.com", session=FakeSession(FakeResponse(503)))

    def test_bad_json_is_inconclusive(self):
        with self.assertRaises(Inconclusive):
            rdap.lookup("ornek.com", session=FakeSession(FakeResponse(200)))


if __name__ == "__main__":
    unittest.main()
