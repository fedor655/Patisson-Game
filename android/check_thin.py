"""Проверить, что телефонный клиент остался тонким.

    python android/check_thin.py

Приложение на телефон собирается из двух файлов. Стоит кому-нибудь
подтянуть туда движок, numpy или саму игру — APK перестанет собираться,
и узнается это через час сборки, а не сразу. Поэтому импорты читаются
разбором кода: искать эти слова текстом нельзя, они честно упоминаются в
комментариях, которые объясняют, почему их здесь нет.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Всё, что телефону позволено знать: стандартная библиотека, Kivy и
# сосед по папке.
ALLOWED = {
    "json", "queue", "socket", "struct", "threading", "sys", "os", "time",
    "math", "traceback", "__future__",
    "kivy",
    "link",                       # плоская раскладка на телефоне
}
# То же самое, но внутри репозитория модуль лежит пакетом.
ALLOWED_RELATIVE = {"link"}

FILES = ("link.py", "main.py")


def top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:                    # from .link import ...
                names.add((node.module or "").split(".")[0])
            elif node.module:
                names.add(node.module.split(".")[0])
    return {n for n in names if n}


def main(folder: str | None = None) -> int:
    where = Path(folder) if folder else Path(__file__).resolve().parents[1] / "patisson2" / "mobile"
    bad: list[str] = []
    for name in FILES:
        path = where / name
        if not path.exists():
            bad.append(f"{name}: файла нет в {where}")
            continue
        extra = top_level_imports(path) - ALLOWED - ALLOWED_RELATIVE
        if extra:
            bad.append(f"{name}: тянет лишнее — {', '.join(sorted(extra))}")
    for line in bad:
        print(f"  ! {line}", flush=True)
    if bad:
        return 1
    print("телефонный клиент тонкий: только стандартная библиотека и Kivy",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
