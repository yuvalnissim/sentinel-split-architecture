import datetime as dt
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("lifetime", Path(__file__).resolve().parents[1] / "scripts/check-credential-lifetime.py")
lifetime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lifetime)


class CredentialLifetimeTests(unittest.TestCase):
    def test_missing_expiration_fails(self):
        with self.assertRaises(ValueError):
            lifetime.remaining_seconds("")

    def test_unzoned_expiration_fails(self):
        with self.assertRaises(ValueError):
            lifetime.remaining_seconds("2026-11-16T12:00:00")

    def test_expiration_uses_utc_offset(self):
        now = dt.datetime(2026, 11, 16, 10, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(lifetime.remaining_seconds("2026-11-16T13:00:00+02:00", now), 3600)

    def test_expired_session_is_negative(self):
        now = dt.datetime(2026, 11, 16, 10, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(lifetime.remaining_seconds("2026-11-16T09:59:00Z", now), -60)
