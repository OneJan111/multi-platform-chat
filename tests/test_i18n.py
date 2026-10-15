import ast
import string
import unittest
from pathlib import Path

from src import i18n, reading, translate, tts


class TranslationCoverageTests(unittest.TestCase):
    def test_static_app_translation_keys_exist(self):
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        tree = ast.parse(app_path.read_text(encoding="utf-8"))
        keys = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id != "t" or not node.args:
                continue
            key = node.args[0]
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                keys.add(key.value)
            elif isinstance(key, ast.Name):
                for parent in ast.walk(tree):
                    if not isinstance(parent, (ast.GeneratorExp, ast.ListComp)) or not isinstance(parent.elt, ast.Call):
                        continue
                    if (not isinstance(parent.elt.func, ast.Name) or parent.elt.func.id != "t"
                            or not parent.elt.args or parent.elt.args[0] is not key):
                        continue
                    for generator in parent.generators:
                        if (isinstance(generator.target, ast.Name) and generator.target.id == key.id
                                and isinstance(generator.iter, (ast.Tuple, ast.List))):
                            keys.update(
                                item.value for item in generator.iter.elts
                                if isinstance(item, ast.Constant) and isinstance(item.value, str)
                            )

        self.assertEqual(sorted(keys - i18n._STRINGS.keys()), [])

    def test_translations_preserve_format_placeholders(self):
        formatter = string.Formatter()
        for key, translations in i18n._STRINGS.items():
            expected = {
                name for _, name, _, _ in formatter.parse(key) if name is not None
            }
            self.assertEqual(len(translations), 2, key)
            for language, translated in zip(("zh", "ja"), translations):
                actual = {
                    name for _, name, _, _ in formatter.parse(translated) if name is not None
                }
                self.assertEqual(actual, expected, f"{language}: {key}")
                self.assertTrue(translated.strip(), f"{language}: {key} is empty")

    def test_reading_aids_toggle_is_localized(self):
        label = "Show pinyin / furigana"
        self.assertEqual(i18n.translate(label, "en"), label)
        self.assertEqual(i18n.translate(label, "zh"), "显示拼音 / 振假名")
        self.assertEqual(i18n.translate(label, "ja"), "ピンイン／振り仮名を表示")

    def test_unthanked_filter_is_localized(self):
        label = "Unthanked"
        self.assertEqual(i18n.translate(label, "en"), label)
        self.assertEqual(i18n.translate(label, "zh"), "未感谢")
        self.assertEqual(i18n.translate(label, "ja"), "未お礼")

    def test_chat_tts_buttons_are_localized(self):
        for label, zh, ja in (
            ("Mute", "静音", "ミュート"),
            ("Unmute", "取消静音", "ミュート解除"),
            ("Emoji", "表情", "絵文字"),
            ("Username", "用户名", "ユーザー名"),
            ("Translated", "译文", "翻訳"),
            ("Read chat translations", "阅读弹幕译文", "チャットの翻訳を読み上げ"),
            ("Read Super Chat translations", "阅读醒目留言译文", "スーパーチャットの翻訳を読み上げ"),
        ):
            self.assertEqual(i18n.translate(label, "en"), label)
            self.assertEqual(i18n.translate(label, "zh"), zh)
            self.assertEqual(i18n.translate(label, "ja"), ja)

    def test_feed_order_options_are_localized(self):
        self.assertEqual(i18n.translate("Newest at top", "zh"), "最新在上")
        self.assertEqual(i18n.translate("Newest at bottom", "zh"), "最新在下")
        self.assertEqual(i18n.translate("⚙️ Global settings", "zh"), "⚙️ 全局设定")

    def test_scroll_to_bottom_is_localized(self):
        self.assertEqual(i18n.translate("Scroll to bottom", "zh"), "滚动到底部")
        self.assertEqual(i18n.translate("Scroll to bottom", "ja"), "一番下までスクロール")
        self.assertEqual(i18n.translate("Scroll to latest", "zh"), "滚动到最新消息")
        self.assertEqual(i18n.translate("Scroll to latest", "ja"), "最新メッセージへスクロール")

    def test_drawer_page_heading_is_localized(self):
        self.assertEqual(i18n.translate("Page", "en"), "Page")
        self.assertEqual(i18n.translate("Page", "zh"), "页面")
        self.assertEqual(i18n.translate("Page", "ja"), "ページ")

    def test_emote_help_combines_site_scope_and_bilibili_send_behavior(self):
        message = (
            "Each site's own emotes are sent only to that site. Clicking a Bilibili special emote sends it "
            "immediately as its own danmaku."
        )
        self.assertEqual(
            i18n.translate(message, "zh"),
            "各网站专属表情包，只发到该网站。点击 B站专属表情包后会立即单独发送为一条弹幕。",
        )

    def test_dynamic_language_and_reading_labels_exist(self):
        labels = set(translate.LANGUAGES.values())
        labels.update(language[0] for language in tts.LANGUAGES.values())
        labels.update(reading.MODES.values())
        self.assertEqual(sorted(labels - i18n._STRINGS.keys()), [])


if __name__ == "__main__":
    unittest.main()
