"""Check physical function length and snake_case in project Python files."""

import ast
import re
from pathlib import Path

FRAMEWORK_NAMES = {
    "setUp",
    "tearDown",
    "setUpClass",
    "tearDownClass",
    "setUpTestData",
}


def check_function(path, node) -> list[str]:
    errors = []
    size = node.end_lineno - node.lineno + 1
    if size > 14:
        errors.append(f"{path}:{node.lineno}: {node.name}: {size} lines")
    if node.name not in FRAMEWORK_NAMES:
        if not re.fullmatch(r"_?[a-z][a-z0-9_]*|__[a-z_]+__", node.name):
            errors.append(f"{path}:{node.lineno}: non-snake-case {node.name}")
    return errors


def check_file(path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        error
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for error in check_function(path, node)
    ]


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    paths = [
        path
        for directory in ("accounts", "videos", "config", "tests", "scripts")
        for path in (root / directory).rglob("*.py")
    ]
    errors = [error for path in paths for error in check_file(path)]
    print("\n".join(errors) if errors else "Code rules passed.")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
