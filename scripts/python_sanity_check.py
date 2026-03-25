from __future__ import annotations

import argparse
import ast
import os
import sys
from pathlib import Path

BAD_LITERALS = {" true": "True", " false": "False", " null": "None"}


def iter_python_files(root: Path):
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in {".git", ".pytest_cache", "__pycache__", ".venv", "venv"}]
        for filename in files:
            if filename.endswith(".py"):
                yield Path(current_root) / filename


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida sintaxe Python e procura literais JSON errados.")
    parser.add_argument("path", nargs="?", default=".", help="Diretório raiz do projeto")
    args = parser.parse_args()

    root = Path(args.path).resolve()
    failures = []

    for file_path in iter_python_files(root):
        text = file_path.read_text(encoding="utf-8")
        compact = f" {text}"
        for bad, correct in BAD_LITERALS.items():
            if bad in compact:
                failures.append(f"{file_path}: literal suspeito {bad.strip()} -> use {correct}")
        try:
            ast.parse(text, filename=str(file_path))
        except SyntaxError as exc:
            failures.append(f"{file_path}: SyntaxError linha {exc.lineno}: {exc.msg}")

    if failures:
        print("Falhas encontradas:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Sanity check concluído sem falhas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
