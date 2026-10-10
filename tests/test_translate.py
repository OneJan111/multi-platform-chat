import unittest
from unittest.mock import Mock, patch

from src import translate


class TranslationProviderTests(unittest.TestCase):
    def test_deepl_batch_uses_auth_and_maps_target_language(self):
        response = Mock()
        response.json.return_value = {
            "translations": [
                {"text": "你好", "detected_source_language": "EN"},
                {"text": "世界", "detected_source_language": "EN"},
            ]
        }
        with (
            patch.object(translate, "TRANSLATION_PROVIDER", "deepl"),
            patch.object(translate, "DEEPL_API_KEY", "test-key"),
            patch.object(translate, "DEEPL_TRANSLATE_URL", "https://api-free.deepl.com/v2/translate"),
            patch.object(translate._session, "post", return_value=response) as post,
        ):
            result = translate.translate_batch(["hello", "world"], "zh-TW")

        self.assertEqual(result, [("你好", "en"), ("世界", "en")])
        post.assert_called_once_with(
            "https://api-free.deepl.com/v2/translate",
            json={"text": ["hello", "world"], "target_lang": "ZH-HANT"},
            headers={"Authorization": "DeepL-Auth-Key test-key"},
            timeout=10.0,
        )
        response.raise_for_status.assert_called_once_with()

    def test_google_provider_remains_default_compatible(self):
        response = Mock()
        response.json.return_value = [["你好", "en"]]
        with (
            patch.object(translate, "TRANSLATION_PROVIDER", "google"),
            patch.object(translate._session, "get", return_value=response) as get,
        ):
            result = translate.translate_batch(["hello"], "zh-CN")

        self.assertEqual(result, [("你好", "en")])
        get.assert_called_once()
        response.raise_for_status.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
