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


class RoutedFakeSession:
    """Returns a different canned response depending on the requested URL,
    for testing the registry -> registrar related-link follow-up."""
    def __init__(self, routes):
        self.routes = routes  # {url_substring: FakeResponse}
        self.calls = []

    def get(self, url, *_args, **_kwargs):
        self.calls.append(url)
        for substring, response in self.routes.items():
            if substring in url:
                return response
        raise AssertionError(f"no route for {url}")


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


class DualSourceTest(unittest.TestCase):
    def _routed(self):
        registry_payload = json.loads((FIX / "rdap_dual_registry.json").read_text())
        registrar_payload = json.loads((FIX / "rdap_dual_registrar.json").read_text())
        return RoutedFakeSession({
            "rdap.verisign.com": FakeResponse(200, registry_payload),
            "example-registrar.com": FakeResponse(200, registrar_payload),
        })

    def test_fresher_registrar_data_wins(self):
        session = self._routed()
        result = rdap.lookup("ornek.com", session=session)
        # registrar summary has the later "last changed" -> its data is used
        self.assertEqual(result.expiration, "2027-08-27T10:24:31Z")
        self.assertEqual(result.statuses, ["auto renew period"])
        self.assertTrue(result.extra["dual_source"])
        self.assertEqual(result.extra["fresher_source"], "registrar")
        self.assertEqual(len(session.calls), 2)

    def test_dual_source_note_mentions_both(self):
        session = self._routed()
        result = rdap.lookup("ornek.com", session=session)
        note = rdap.format_dual_source(result.extra)
        self.assertIn("2026-08-27T10:24:31Z", note)  # stale registry value
        self.assertIn("2027-08-27T10:24:31Z", note)  # fresh registrar value
        self.assertIn("Registrar", note)

    def test_registrar_fetch_failure_keeps_registry_result(self):
        registry_payload = json.loads((FIX / "rdap_dual_registry.json").read_text())
        session = RoutedFakeSession({
            "rdap.verisign.com": FakeResponse(200, registry_payload),
            "example-registrar.com": FakeResponse(503),
        })
        result = rdap.lookup("ornek.com", session=session)
        self.assertEqual(result.expiration, "2026-08-27T10:24:31Z")
        self.assertFalse(result.extra.get("dual_source"))
        self.assertIsNone(rdap.format_dual_source(result.extra))

    def test_no_related_link_is_single_source(self):
        payload = json.loads((FIX / "rdap_registered.json").read_text())
        result = rdap.lookup("ornek.com", session=FakeSession(FakeResponse(200, payload)))
        self.assertNotIn("dual_source", result.extra)
        self.assertIsNone(rdap.format_dual_source(result.extra))


if __name__ == "__main__":
    unittest.main()
