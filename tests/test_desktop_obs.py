import unittest

import desktop_app
from src import i18n


def english(text, **kwargs):
    return i18n.translate(text, "en", **kwargs)


class ObsConnectionMessageTests(unittest.TestCase):
    def test_missing_library(self):
        message, detail = desktop_app._obs_connection_message(("no_lib", ""), "localhost", 4455, english)
        self.assertIn("obsws-python is not installed", message)
        self.assertEqual(detail, "")

    def test_missing_password(self):
        message, _ = desktop_app._obs_connection_message(("no_password", ""), "localhost", 4455, english)
        self.assertIn("OBS_PASSWORD is not set", message)

    def test_auth_failure_includes_address_and_detail(self):
        message, _ = desktop_app._obs_connection_message(("auth", "bad pw"), "pc", 4455, english)
        self.assertIn("pc:4455", message)
        self.assertIn("bad pw", message)

    def test_unreachable_has_firewall_hint(self):
        message, detail = desktop_app._obs_connection_message(("unreachable", ""), "pc", 4460, english)
        self.assertIn("nothing answered at pc:4460", message)
        self.assertIn("4460", detail)

    def test_translated(self):
        message, _ = desktop_app._obs_connection_message(
            ("no_password", ""), "localhost", 4455, lambda text, **kw: i18n.translate(text, "zh", **kw)
        )
        self.assertNotIn("is not set", message)


class ObsChatUpdateDueTests(unittest.TestCase):
    def test_changed_text_is_due(self):
        self.assertTrue(desktop_app._obs_chat_update_due(("src", "a"), 100.0, "src", "b", 101.0))

    def test_same_text_skipped_within_30_seconds(self):
        self.assertFalse(desktop_app._obs_chat_update_due(("src", "a"), 100.0, "src", "a", 129.0))

    def test_same_text_refreshed_after_30_seconds(self):
        self.assertTrue(desktop_app._obs_chat_update_due(("src", "a"), 100.0, "src", "a", 130.0))

    def test_first_push_is_due(self):
        self.assertTrue(desktop_app._obs_chat_update_due(None, 0.0, "src", "", 1.0))


if __name__ == "__main__":
    unittest.main()
