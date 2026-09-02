import unittest

import watcher


class WatcherTests(unittest.TestCase):
    def test_extracts_markers_from_html_and_headers(self):
        cards, signals, priorities = watcher.extract_markers(
            "<!-- [CARD 02/20] [SIGNAL 17/16] [PRIORITY 2/3] -->",
            {"X-Signal-09-Of-16": "payload"},
        )
        self.assertEqual(cards, {2})
        self.assertEqual(signals, {9, 17})
        self.assertEqual(priorities, {"2"})

    def test_discovers_internal_pages_and_media_only(self):
        html = '''
            <a href="/covenant.html">Rules</a>
            <a href="https://example.com/nope.html">Nope</a>
            <!-- /media/4379e88b023ef119.wav -->
            <img src="/media/9b41c7.jpg">
        '''
        pages, media = watcher.discover_links(html, watcher.BASE_URL)
        self.assertIn(watcher.BASE_URL.rstrip("/") + "/covenant.html", pages)
        self.assertEqual(len(media), 2)
        self.assertTrue(all("/media/" in item for item in media))

    def test_associates_nearby_media_with_card(self):
        text = "[CARD 07/20] [/media/secret.wav]"
        self.assertEqual(
            watcher.card_for_media(text, watcher.BASE_URL.rstrip("/") + "/media/secret.wav"),
            7,
        )

    def test_volatile_headers_do_not_create_noise(self):
        stable = watcher.stable_headers({
            "Date": "today", "Age": "1", "Cache-Status": "hit; ttl=2",
            "Content-Length": "42", "Transfer-Encoding": "chunked",
            "ETag": "abc", "X-Signal-09-Of-16": "payload"
        })
        self.assertNotIn("date", stable)
        self.assertNotIn("age", stable)
        self.assertNotIn("cache-status", stable)
        self.assertNotIn("content-length", stable)
        self.assertNotIn("transfer-encoding", stable)
        self.assertEqual(stable["etag"], "abc")
        self.assertEqual(stable["x-signal-09-of-16"], "payload")


if __name__ == "__main__":
    unittest.main()
