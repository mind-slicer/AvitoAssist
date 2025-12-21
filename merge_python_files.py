#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для объединения всех .py файлов из указанных директорий в один файл.
"""
import os
import sys
from pathlib import Path
from datetime import datetime


def collect_py_files(root_dirs, recursive=True):
    """
    Собирает все .py файлы из указанных директорий.

    Args:
        root_dirs: список директорий для поиска
        recursive: рекурсивный поиск (по умолчанию True)

    Returns:
        список путей к .py файлам
    """
    py_files = []

    for root_dir in root_dirs:
        root_path = Path(root_dir)

        if not root_path.exists():
            print(f"Предупреждение: директория {root_dir} не существует")
            continue

        if recursive:
            # Рекурсивный поиск всех .py файлов
            py_files.extend(root_path.rglob("*.py"))
        else:
            # Только в текущей директории
            py_files.extend(root_path.glob("*.py"))

    # Сортируем для предсказуемого порядка
    return sorted(py_files)


def merge_py_files(py_files, output_file, base_dir=None):
    """
    Объединяет .py файлы в один с разделителями.

    Args:
        py_files: список путей к .py файлам
        output_file: имя выходного файла
        base_dir: базовая директория для относительных путей
    """
    if not py_files:
        print("Не найдено ни одного .py файла!")
        return

    with open(output_file, 'w', encoding='utf-8') as out:
        # Заголовок
        out.write(f"# Объединенный файл Python скриптов\n")
        out.write(f"# Создан: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        out.write(f"# Всего файлов: {len(py_files)}\n")
        out.write("=" * 80 + "\n\n")

        for idx, py_file in enumerate(py_files, 1):
            # Определяем относительный путь
            if base_dir:
                try:
                    relative_path = py_file.relative_to(base_dir)
                except ValueError:
                    relative_path = py_file
            else:
                relative_path = py_file

            # Разделитель файла
            out.write("#" + ("=" * 80) + "\n\n")
            out.write(f"# Файл {idx}/{len(py_files)}: {relative_path}\n")
            out.write("#" + ("=" * 80) + "\n\n")

            # Читаем и записываем содержимое файла
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    out.write(content)

                    # Добавляем пустую строку в конце, если её нет
                    if content and not content.endswith('\n'):
                        out.write('\n')
            except Exception as e:
                out.write(f"# ОШИБКА при чтении файла: {e}\n")
                print(f"Ошибка при чтении {py_file}: {e}")

        # Финальный разделитель
        out.write("\n" + "=" * 80 + "\n")
        out.write(f"# Конец объединенного файла\n")
        out.write("=" * 80 + "\n")

    print(f"✓ Объединено {len(py_files)} файлов в '{output_file}'")


def main():
    """Основная функция."""
    print("=" * 80)
    print("Скрипт объединения Python файлов")
    print("=" * 80)

    # Режим работы
    print("\nВыберите режим работы:")
    print("1. Автоматический (текущая директория скрипта)")
    print("2. Указать директории вручную")

    choice = input("\nВаш выбор (1/2): ").strip()

    directories = []
    base_dir = None

    if choice == "1":
        # Текущая директория скрипта
        script_dir = Path(__file__).parent.resolve()
        directories = [script_dir]
        base_dir = script_dir
        print(f"\nБудет выполнен поиск в: {script_dir}")

    elif choice == "2":
        # Ручной ввод директорий
        print("\nВведите пути к директориям (по одному на строку).")
        print("Для завершения ввода оставьте строку пустой и нажмите Enter.")

        while True:
            dir_path = input("Директория: ").strip()
            if not dir_path:
                break
            directories.append(Path(dir_path))

        if not directories:
            print("Не указано ни одной директории!")
            return

        # Базовая директория - общий родитель
        base_dir = directories[0] if len(directories) == 1 else None

    else:
        print("Неверный выбор!")
        return

    # Рекурсивный поиск?
    recursive_choice = input("\nРекурсивный поиск по подпапкам? (y/n, по умолчанию y): ").strip().lower()
    recursive = recursive_choice != 'n'

    # Имя выходного файла
    output_default = "merged_python_files.py"
    output_file = input(f"\nИмя выходного файла (по умолчанию '{output_default}'): ").strip()
    if not output_file:
        output_file = output_default

    # Собираем и объединяем файлы
    print(f"\nПоиск .py файлов...")
    py_files = collect_py_files(directories, recursive=recursive)

    # Исключаем сам скрипт и выходной файл
    script_path = Path(__file__).resolve()
    output_path = Path(output_file).resolve()
    py_files = [f for f in py_files if f.resolve() != script_path and f.resolve() != output_path]

    if not py_files:
        print("\nНе найдено .py файлов для объединения!")
        return

    print(f"\nНайдено файлов: {len(py_files)}")

    # Показываем список файлов
    show_list = input("Показать список файлов? (y/n): ").strip().lower()
    if show_list == 'y':
        for i, f in enumerate(py_files, 1):
            print(f"  {i}. {f}")

    # Подтверждение
    confirm = input(f"\nОбъединить {len(py_files)} файлов в '{output_file}'? (y/n): ").strip().lower()
    if confirm == 'y':
        merge_py_files(py_files, output_file, base_dir)
        print(f"\n✓ Готово! Результат сохранен в '{output_file}'")
    else:
        print("\nОтменено пользователем.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем.")
        sys.exit(0)
    except Exception as e:
        print(f"\nОшибка: {e}")
        sys.exit(1)
