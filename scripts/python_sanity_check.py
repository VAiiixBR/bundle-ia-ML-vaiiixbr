import os
import sys

# Literais inválidos em Python quando vieram de JSON
BAD_LITERALS = {
    " true": "True",
    " false": "False",
    " null": "None",
    ": true": ": True",
    ": false": ": False",
    ": null": ": None",
}

EXTENSIONS = (".py",)


def scan_file(path: str):
    issues = []

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return issues

    for bad, correct in BAD_LITERALS.items():
        if bad in content:
            issues.append((bad, correct))

    return issues


def should_skip(path: str) -> bool:
    normalized = os.path.normpath(path).lower()
    return normalized.endswith(os.path.normpath("scripts/python_sanity_check.py").lower())


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    total_issues = 0

    print(f"\n[Sanity Check] Escaneando: {os.path.abspath(root)}\n")

    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            if not filename.endswith(EXTENSIONS):
                continue

            full_path = os.path.join(dirpath, filename)

            # Ignora o próprio script, senão ele acusa os padrões que procura
            if should_skip(full_path):
                continue

            issues = scan_file(full_path)

            if issues:
                print(f"[ERRO] {full_path}")
                for bad, correct in issues:
                    print(f"   encontrado: {bad!r} -> use {correct!r}")
                    total_issues += 1

    if total_issues == 0:
        print("✔ Nenhum erro de literal encontrado.\n")
        return 0

    print(f"\n✖ {total_issues} problemas encontrados.\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())