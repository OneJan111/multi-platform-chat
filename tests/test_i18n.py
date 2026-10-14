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

    def test_dynamic_language_and_reading_labels_exist(self):
        labels = set(translate.LANGUAGES.values())
        labels.update(language[0] for language in tts.LANGUAGES.values())
        labels.update(reading.MODES.values())
        self.assertEqual(sorted(labels - i18n._STRINGS.keys()), [])


if __name__ == "__main__":
    unittest.main()
