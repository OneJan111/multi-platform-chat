import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from desktop_app import DesktopEmoteCache, _submit_emote_image_loads


class DesktopEmoteImageLoadingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache = DesktopEmoteCache(Path(self.temp_dir.name) / "emote_cache.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cached_image_is_reported_before_slow_download_finishes(self):
        self.cache.set_image("https://example.test/cached.png", b"cached")
        release_download = threading.Event()
        cached_reported = threading.Event()
        finished = threading.Event()
        results = []

        def download(url):
            release_download.wait(timeout=5)
            return b"downloaded"

        def on_result(result):
            results.append(result)
            if result[0] == 0:
                cached_reported.set()

        with ThreadPoolExecutor(max_workers=2) as pool:
            _submit_emote_image_loads(
                pool,
                [
                    (0, "https://example.test/cached.png"),
                    (1, "https://example.test/slow.png"),
                ],
                self.cache,
                on_result,
                finished.set,
                lambda: False,
                download,
            )
            self.assertTrue(cached_reported.wait(timeout=2))
            self.assertFalse(finished.is_set())
            release_download.set()
            self.assertTrue(finished.wait(timeout=2))

        self.assertIn((0, b"cached", ""), results)
        self.assertIn((1, b"downloaded", ""), results)
        self.assertEqual(
            self.cache.get_image("https://example.test/slow.png"), b"downloaded"
        )

    def test_cancelled_loads_do_not_download_or_report_images(self):
        downloads = []
        results = []
        finished = threading.Event()

        with ThreadPoolExecutor(max_workers=2) as pool:
            _submit_emote_image_loads(
                pool,
                [(0, "https://example.test/one.png")],
                self.cache,
                results.append,
                finished.set,
                lambda: True,
                lambda url: downloads.append(url) or b"image",
            )
            self.assertTrue(finished.wait(timeout=2))

        self.assertEqual(downloads, [])
        self.assertEqual(results, [])

    def test_cache_keeps_a_large_room_of_emote_images(self):
        for index in range(705):
            self.assertEqual(
                self.cache.set_image(f"https://example.test/{index}.png", b"x"),
                "",
            )
        self.assertEqual(self.cache.prune_images(), "")

        self.assertEqual(len(list(self.cache.image_dir.glob("*.img"))), 705)


if __name__ == "__main__":
    unittest.main()
