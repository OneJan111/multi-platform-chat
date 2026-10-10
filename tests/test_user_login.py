import base64
import hashlib
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cryptography.fernet import Fernet
from src import bilibili as bili
from src import browser_cookies as bc
from src import missevan as me
from src import user_login as ul
from src import youtube_web as ytw


class UserLoginTests(unittest.TestCase):
    def test_logins_are_isolated_per_user(self):
        alice, bob = {}, {}
        with ul.using(alice):
            ytw.save_login({"SAPISID": "a", "SID": "b"})
            ytw.select_channel("page-1")
            bc.save_bilibili_credentials({"SESSDATA": "s", "bili_jct": "j", "unrelated": "x"})
            me.save_login({"token": "t"})
        with ul.using(bob):
            self.assertFalse(ytw.has_login())
            self.assertEqual(ytw.selected_page_id(), "")
            self.assertFalse(bili.has_login_credentials())
            self.assertFalse(me.has_login())
        with ul.using(alice):
            self.assertTrue(ytw.has_login())
            self.assertEqual(ytw.selected_page_id(), "page-1")
            self.assertEqual(ul.get("bilibili"), {"SESSDATA": "s", "bili_jct": "j"})
            self.assertTrue(me.has_login())

    def test_listeners_keep_the_starting_users_login(self):
        with ul.using({"bilibili": {"SESSDATA": "s"}, "missevan": {"token": "t"}}):
            b, m = bili.DanmakuListener("1"), me.MissEvanListener("2")
        self.assertEqual(b._login[0], "s")
        self.assertEqual(m._cookies, {"token": "t"})

    def test_clear_login(self):
        logins = {}
        with ul.using(logins):
            ytw.save_login({"SAPISID": "a"})
            ytw.select_channel("p")
            self.assertTrue(ul.take_changed())
            self.assertFalse(ul.take_changed())
            self.assertTrue(bc.clear_login("youtube"))
            self.assertFalse(ytw.has_login())
            self.assertEqual(ytw.selected_page_id(), "")
            self.assertTrue(ul.take_changed())

    def test_browser_cookie_round_trip(self):
        logins = {"youtube": {f"c{i}": "v" * 300 for i in range(30)}, "youtube_page_id": "p", "_changed": True}
        token = ul.encode(logins)
        self.assertNotIn("vvvv", token)
        chunks = ul.split_token(token)
        jar = {f"{ul.COOKIE_NAME}_{i}": c for i, c in enumerate(chunks)}
        jar[f"{ul.COOKIE_NAME}_n"] = str(len(chunks))
        self.assertEqual(ul.decode(ul.join_cookies(jar)), {"youtube": logins["youtube"], "youtube_page_id": "p"})

    def test_bad_cookie_is_ignored(self):
        token = ul.encode({"missevan": {"token": "t"}})
        self.assertEqual(ul.decode(token[:-4] + "AAAA"), {})
        self.assertEqual(ul.decode("garbage"), {})
        self.assertEqual(ul.join_cookies({f"{ul.COOKIE_NAME}_n": "2", f"{ul.COOKIE_NAME}_0": "x"}), "")
        self.assertEqual(ul.encode({}), "")

    def test_fernet_uses_streamlit_toml_secret(self):
        with TemporaryDirectory() as temp_dir:
            secret_file = Path(temp_dir) / ".login_secret"
            with (
                patch.dict(os.environ, {"LOGIN_SECRET": ""}),
                patch("streamlit.secrets", {"LOGIN_SECRET": "toml-secret"}),
                patch.object(ul, "_SECRET_FILE", secret_file),
            ):
                expected = Fernet(
                    base64.urlsafe_b64encode(hashlib.sha256(b"toml-secret").digest())
                )
                token = ul._fernet().encrypt(b"test")
                self.assertEqual(expected.decrypt(token), b"test")
                self.assertFalse(secret_file.exists())

    def test_detect_site_from_pasted_cookies(self):
        self.assertEqual(bc.detect_site("SESSDATA=a; bili_jct=b"), "Bilibili")
        self.assertEqual(bc.detect_site("Cookie: SID=a; SAPISID=b"), "YouTube")
        self.assertIsNone(bc.detect_site("token=a; FM_SESS=b"))
        self.assertIsNone(bc.detect_site(""))
        self.assertIsNone(bc.detect_site("[not json"))
        self.assertEqual(bc.detect_site('[{"name": "token", "value": "x", "domain": ".missevan.com"}]'), "MissEvan")
        netscape = ".youtube.com\tTRUE\t/\tTRUE\t0\tSAPISID\tx\n.bilibili.com\tTRUE\t/\tTRUE\t0\tbuvid3\ty"
        self.assertEqual(bc.detect_site(netscape), "YouTube")
        both = netscape + "\n.bilibili.com\tTRUE\t/\tTRUE\t0\tSESSDATA\tz"
        self.assertIsNone(bc.detect_site(both))


if __name__ == "__main__":
    unittest.main()
