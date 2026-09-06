import ast
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BACKEND = Path(settings.BASE_DIR)
SKIP = frozenset({"__pycache__", "migrations", ".venv", "venv"})


def python_files():
    for path in sorted(BACKEND.rglob("*.py")):
        if not any(part in SKIP for part in path.relative_to(BACKEND).parts):
            yield path


def called_name(node):
    return getattr(node.func, "id", None) or getattr(node.func, "attr", None)


def argless_format_html_calls():
    found = []
    for path in python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and called_name(node) == "format_html":
                if not node.args[1:] and not node.keywords:
                    found.append(f"{path.relative_to(BACKEND)}:{node.lineno}")
    return found


class FormatHtmlCallsCarryArgumentsTest(SimpleTestCase):

    def test_no_call_passes_a_template_with_nothing_to_interpolate(self):
        self.assertEqual(
            argless_format_html_calls(),
            [],
            "format_html with no interpolation arguments is a TypeError from Django 6. "
            "A constant badge is mark_safe; a value is format_html with a placeholder.",
        )

    def test_the_scan_finds_a_call_it_should_reject(self):
        tree = ast.parse("format_html('<b>Eligible</b>')")
        call = tree.body[0].value

        self.assertEqual(called_name(call), "format_html")
        self.assertFalse(call.args[1:] or call.keywords)
