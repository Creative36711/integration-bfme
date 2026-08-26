#!/usr/bin/env python3
"""
Собрать МИНИМАЛЬНЫЙ архив калибратора для раздачи (вариант с calibrate.bat).

В архив попадает только то, что реально нужно tools/calibrate.py: сам скрипт,
замыкание его импортов из bridge/ и tools/, calibrate.bat, config/config.json
и инструкция. Ни main.py, ни menu/room/spawn, ни numpy — bat поставит numpy
сам при первом запуске.

Состав вычисляется, а не задаётся списком: скрипт разбирает импорты через ast
и идёт по ним рекурсивно, поэтому добавление нового модуля в bridge/
автоматически попадёт в архив.

После сборки архив ПРОВЕРЯЕТСЯ: замыкание импортов пересчитывается уже внутри
собранной папки, и если какого-то модуля там нет — сборка падает.

Запуск (на любой ОС, только stdlib):
    python packaging/make_calibrate_zip.py
    python packaging/make_calibrate_zip.py --out dist/My.zip --keep
"""

import argparse
import ast
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_PACKAGES = ("bridge", "tools")
BUNDLE_NAME = "Calibrate"

# Не-питоновские файлы, которые кладём в архив вручную.
EXTRA_FILES = [
    ("calibrate.bat", "calibrate.bat"),
    ("packaging/bat_readme.txt", "README.txt"),
    ("config/config.json", "config/config.json"),
]


def _local_imports(path):
    """Локальные модули, которые импортирует файл (включая ленивые импорты)."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)

    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            found.add(node.module)
            # `from bridge import config` — это модуль bridge.config
            found.update(f"{node.module}.{alias.name}" for alias in node.names)

    return {m for m in found if m.split(".")[0] in LOCAL_PACKAGES}


def import_closure(root, entry="tools.calibrate"):
    """Все локальные модули, нужные entry, в виде относительных путей .py."""
    seen, stack = set(), [entry]
    while stack:
        mod = stack.pop()
        if mod in seen:
            continue
        seen.add(mod)
        path = os.path.join(root, *mod.split(".")) + ".py"
        if os.path.exists(path):
            stack.extend(_local_imports(path) - seen)

    files = set()
    for mod in seen:
        rel = os.path.join(*mod.split(".")) + ".py"
        if os.path.exists(os.path.join(root, rel)):
            files.add(rel.replace(os.sep, "/"))
    # __init__.py пакетов обязательны, даже если их никто не импортирует явно
    for pkg in LOCAL_PACKAGES:
        init = f"{pkg}/__init__.py"
        if os.path.exists(os.path.join(root, *init.split("/"))):
            files.add(init)
    return sorted(files)


def build(dest, root=ROOT):
    """Сложить файлы в папку dest. Возвращает список относительных путей."""
    if os.path.exists(dest):
        shutil.rmtree(dest)
    written = []

    for rel in import_closure(root):
        target = os.path.join(dest, *rel.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(root, *rel.split("/")), target)
        written.append(rel)

    for src, dst in EXTRA_FILES:
        source = os.path.join(root, *src.split("/"))
        if not os.path.exists(source):
            raise FileNotFoundError(f"нет обязательного файла: {src}")
        target = os.path.join(dest, *dst.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)
        written.append(dst)

    return sorted(written)


def verify(dest):
    """Пересчитать замыкание импортов ВНУТРИ собранной папки.

    Возвращает список того, чего не хватает (пустой = архив рабочий).
    """
    missing = []
    for rel in import_closure(dest):
        if not os.path.exists(os.path.join(dest, *rel.split("/"))):
            missing.append(rel)
    for rel in ("calibrate.bat", "config/config.json", "README.txt"):
        if not os.path.exists(os.path.join(dest, *rel.split("/"))):
            missing.append(rel)

    bat = os.path.join(dest, "calibrate.bat")
    if os.path.exists(bat):
        raw = open(bat, "rb").read()
        if raw.count(b"\n") != raw.count(b"\r\n"):
            missing.append("calibrate.bat: окончания строк не CRLF")
    return missing


def make_zip(folder, zip_path):
    if os.path.exists(zip_path):
        os.remove(zip_path)
    base = os.path.basename(folder.rstrip("/\\"))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _dirnames, filenames in os.walk(folder):
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, folder).replace(os.sep, "/")
                zf.write(full, f"{base}/{rel}")
    return zip_path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--out", default=os.path.join(ROOT, "dist",
                                                  "CalibratePortable.zip"))
    ap.add_argument("--keep", action="store_true",
                    help="не удалять распакованную папку после упаковки")
    args = ap.parse_args(argv)

    dist = os.path.dirname(os.path.abspath(args.out)) or ROOT
    os.makedirs(dist, exist_ok=True)
    folder = os.path.join(dist, BUNDLE_NAME)

    print("[pack] собираю", folder)
    files = build(folder)
    for rel in files:
        print(f"         + {rel}")

    missing = verify(folder)
    if missing:
        print("\n[pack] ОШИБКА: в архиве не хватает:", file=sys.stderr)
        for item in missing:
            print(f"         - {item}", file=sys.stderr)
        return 1

    zip_path = make_zip(folder, args.out)
    size = os.path.getsize(zip_path)
    print(f"\n[pack] готово: {zip_path}  ({size} байт, файлов: {len(files)})")
    print("[pack] передай этот архив: распаковать -> двойной клик по "
          f"{BUNDLE_NAME}\\calibrate.bat")

    if not args.keep:
        shutil.rmtree(folder, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
