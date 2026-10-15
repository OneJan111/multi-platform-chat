import ast
import unittest
from pathlib import Path
from types import SimpleNamespace


class ClearChatHistoryTests(unittest.TestCase):
    def test_clear_removes_only_thanked_paid_items(self):
        tree = ast.parse(
            (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
        )
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_clear_chat_history"
        )
        pending = {"id": "pending", "type": "superchat", "text": "Keep"}
        state = {
            "chat_messages": [{"id": "chat"}],
            "join_messages": [{"id": "join"}],
            "paid_messages": [
                {"id": "gift", "type": "gift"},
                {"id": "superchat", "type": "superchat"}, pending,
            ],
            "thanked_ids": {"gift", "superchat", "old"},
        }
        namespace = {"st": SimpleNamespace(session_state=state)}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "app.py", "exec"), namespace)
        for _ in range(2):
            namespace["_clear_chat_history"]()
            self.assertEqual(state["chat_messages"], [])
            self.assertEqual(state["join_messages"], [])
            self.assertEqual(state["paid_messages"], [pending])
            self.assertEqual(state["thanked_ids"], set())


if __name__ == "__main__":
    unittest.main()
