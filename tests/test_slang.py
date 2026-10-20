import unittest
from unittest.mock import Mock, patch

from src import slang, translate


class StreamingSlangTests(unittest.TestCase):
    def test_glossary_overrides_terms_inside_mixed_text(self):
        self.assertEqual(
            slang.apply("感谢舰长续费！欢迎上舰", "en"),
            "感谢renew a Captain membership！欢迎become a Captain member",
        )
        self.assertEqual(slang.apply("Super Chat 来了", "zh-CN"), "醒目留言 来了")
        self.assertEqual(slang.apply("普通文字", "en"), "普通文字")

    def test_latin_terms_match_case_insensitively_without_partial_words(self):
        self.assertEqual(slang.apply("Super CHAT!", "ja"), "スーパーチャット!")
        self.assertEqual(slang.apply("superchatting", "ja"), "superchatting")

    def test_google_translation_restores_glossary_override(self):
        response = Mock()
        response.json.return_value = [[
            "Thanks MPCGLOSSARYTOKEN0END, welcome MPCGLOSSARYTOKEN1END", "zh-CN",
        ]]
        with (
            patch.object(translate, "INDEX_TRANSLATE_API_BASE", ""),
            patch.object(translate._session, "get", return_value=response) as get,
        ):
            result = translate.translate_batch(["感谢舰长续费，欢迎上舰"], "en")

        request_text = dict(get.call_args.kwargs["params"])["q"]
        self.assertNotIn("舰长续费", request_text)
        self.assertNotIn("上舰", request_text)
        self.assertIn("Thanks", result[0][0])
        self.assertIn("renew a Captain membership", result[0][0])
        self.assertIn("become a Captain member", result[0][0])

    def test_japanese_translation_restores_localized_glossary_marker(self):
        response = Mock()
        response.json.return_value = [["MPC用語集TOKEN0END", "zh-CN"]]
        with (
            patch.object(translate, "INDEX_TRANSLATE_API_BASE", ""),
            patch.object(translate._session, "get", return_value=response),
        ):
            result = translate.translate_batch(["舰长"], "ja")

        self.assertEqual(result, [("キャプテン", "zh-CN")])


if __name__ == "__main__":
    unittest.main()
