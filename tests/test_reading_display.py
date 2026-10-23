import unittest
from unittest.mock import patch

import desktop_app
from src import reading


class RubyHtmlTests(unittest.TestCase):
    def test_desktop_chat_text_is_plain_until_reading_tooltip_is_requested(self):
        self.assertEqual(
            desktop_app._plain_chat_html("<你好>\nhello"),
            "&lt;你好&gt;<br>hello",
        )

    def test_plain_readings_are_available_for_hover_tooltips(self):
        with patch.object(
            reading,
            "segments",
            return_value=(("用", "yòng"), ("語", "yǔ"), ("集", "jí"), ("! ", "")),
        ):
            self.assertEqual(
                reading.with_readings("用語集! "),
                "用（yòng）語（yǔ）集（jí）! ",
            )

    def test_plain_readings_leave_unannotated_text_unchanged(self):
        with patch.object(reading, "segments", return_value=()):
            self.assertEqual(reading.with_readings("hello"), "hello")

    def test_reading_is_rendered_above_corresponding_escaped_text(self):
        with patch.object(
            reading,
            "segments",
            return_value=(("<你", "nǐ"), ("好>", "hǎo")),
        ):
            rendered = reading.ruby_html("<你好>")

        self.assertEqual(
            rendered,
            '<table cellspacing="0" cellpadding="0" border="0">'
            "<tr>"
            '<td align="center" valign="bottom"><small>nǐ</small></td>'
            '<td align="center" valign="bottom"><small>hǎo</small></td>'
            "</tr>"
            "<tr>"
            '<td align="center">&lt;你</td>'
            '<td align="center">好&gt;</td>'
            "</tr>"
            "</table>",
        )

    def test_unannotated_text_is_escaped_and_keeps_line_breaks(self):
        with patch.object(reading, "segments", return_value=()):
            rendered = reading.ruby_html("<hello>\nworld")

        self.assertEqual(rendered, "&lt;hello&gt;<br>world")

    def test_annotated_text_preserves_spacing_and_line_breaks(self):
        with patch.object(
            reading,
            "segments",
            return_value=(("hello world", ""), ("\n", ""), ("!", "reading")),
        ):
            rendered = reading.ruby_html("hello world\n!")

        self.assertIn("<small>reading</small>", rendered)
        self.assertIn('<td align="center">hello</td>', rendered)
        self.assertIn('<td align="center">&nbsp;</td>', rendered)
        self.assertIn('<td align="center">world</td>', rendered)
        self.assertIn('<td align="center">!</td>', rendered)
        self.assertGreaterEqual(rendered.count("<tr>"), 4)

    def test_annotated_text_splits_into_rows_to_fit_available_width(self):
        annotated = tuple((char, f"reading{index}") for index, char in enumerate("你好世界和平"))
        with patch.object(reading, "segments", return_value=annotated):
            rendered = reading.ruby_html(
                "你好世界和平", max_width=60, font_size=10
            )

        self.assertGreater(rendered.count("<tr>"), 2)

    def test_measured_widths_fill_the_line_and_rows_use_separate_tables(self):
        annotated = (("ab", ""), ("你", "nǐ"), ("cd", ""))
        with patch.object(reading, "segments", return_value=annotated):
            one_line = reading.ruby_html(
                "ab你cd", max_width=100, font_size=40, measure=lambda text, _: 10 * len(text)
            )
            wrapped = reading.ruby_html(
                "ab你cd", max_width=30, font_size=40, measure=lambda text, _: 10 * len(text)
            )

        self.assertEqual(one_line.count("<table"), 1)
        self.assertGreater(wrapped.count("<table"), 1)
        self.assertEqual(wrapped.count("<table"), wrapped.count("</table>"))


if __name__ == "__main__":
    unittest.main()
