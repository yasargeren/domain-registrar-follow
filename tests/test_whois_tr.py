import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DB_PATH", "./data/test-domains.db")

from app.providers import whois_tr
from app.providers.base import Inconclusive, RateLimited

FIX = Path(__file__).parent / "fixtures"


class WhoisTrParseTest(unittest.TestCase):
    def test_registered_domain(self):
        result = whois_tr.parse("ornek2.com.tr", (FIX / "nic_tr_registered.txt").read_text())
        self.assertFalse(result.available)
        self.assertEqual(result.expiration, "2026-03-12T00:00:00+00:00")
        self.assertEqual(result.created, "2019-03-12T00:00:00+00:00")
        self.assertEqual(result.registrar, "Ornek Kayit Kurulusu A.S.")
        self.assertEqual(result.nameservers, ["ns1.ornekdns.com", "ns2.ornekdns.com"])
        self.assertEqual(result.source, "whois.nic.tr")

    def test_free_domain(self):
        result = whois_tr.parse("ornek2.com.tr", (FIX / "nic_tr_free.txt").read_text())
        self.assertTrue(result.available)
        self.assertEqual(result.statuses, ["available"])

    def test_rate_limit_is_not_availability(self):
        with self.assertRaises(RateLimited):
            whois_tr.parse("ornek2.com.tr", (FIX / "nic_tr_ratelimit.txt").read_text())

    def test_empty_response_is_inconclusive(self):
        with self.assertRaises(Inconclusive):
            whois_tr.parse("ornek2.com.tr", "   \n  ")

    def test_garbage_response_is_inconclusive(self):
        with self.assertRaises(Inconclusive):
            whois_tr.parse("ornek2.com.tr", "some unrelated banner text\nwith no fields")

    def test_date_formats(self):
        self.assertEqual(whois_tr.parse_date("2026-Mar-12."), "2026-03-12T00:00:00+00:00")
        self.assertEqual(whois_tr.parse_date(" 2026-03-12 "), "2026-03-12T00:00:00+00:00")
        self.assertIsNone(whois_tr.parse_date("bilinmiyor"))
        self.assertIsNone(whois_tr.parse_date(""))


if __name__ == "__main__":
    unittest.main()
