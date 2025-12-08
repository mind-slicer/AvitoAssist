import os
import sys
import argparse

def should_ignore(path, ignore_dirs):
    """Проверяет, нужно ли игнорировать путь."""
    basename = os.path.basename(path)
    return basename in ignore_dirs

def generate_tree(startpath, ignore_dirs=None, prefix='', output_file=None):
    if ignore_dirs is None:
        ignore_dirs = set()
    if should_ignore(startpath, ignore_dirs):
        return

    try:
        entries = sorted(os.listdir(startpath))
    except PermissionError:
        print(f"[Нет доступа] {startpath}", file=output_file or sys.stdout)
        return

    dirs = []
    files = []
    for entry in entries:
        full_path = os.path.join(startpath, entry)
        if os.path.isdir(full_path):
            dirs.append(entry)
        else:
            files.append(entry)

    all_items = dirs + files
    total = len(all_items)

    for i, entry in enumerate(all_items):
        full_path = os.path.join(startpath, entry)
        is_last = (i == total - 1)
        connector = '└── ' if is_last else '├── '

        if os.path.isdir(full_path):
            if should_ignore(full_path, ignore_dirs):
                continue
            line = prefix + connector + entry + '/'
            print(line, file=output_file or sys.stdout)
            extension = '    ' if is_last else '│   '
            generate_tree(full_path, ignore_dirs, prefix + extension, output_file)
        else:
            line = prefix + connector + entry
            print(line, file=output_file or sys.stdout)

def main():
    parser = argparse.ArgumentParser(description="Сохраняет иерархию папок в tree.txt")
    parser.add_argument("root", nargs="?", default=".", help="Корневая папка (по умолчанию — текущая)")
    parser.add_argument("--ignore", nargs="*", default=[], help="Список папок для игнорирования")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    ignore_set = set(args.ignore)

    output_path = os.path.join(root, "tree.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"Иерархия папок: {root}\n")
        f.write("=" * 50 + "\n")
        generate_tree(root, ignore_dirs=ignore_set, output_file=f)

    print(f"Иерархия сохранена в {output_path}")

if __name__ == "__main__":
    main()