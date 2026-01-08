import os
import ast
import argparse
import subprocess
import time
import re
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.tree import Tree

console = Console()

class ProjectMapper:
    def __init__(self, root_dir, ignore_list, full_files):
        self.root_dir = os.path.abspath(root_dir)
        self.ignore_list = ignore_list
        self.full_files = full_files
        self.repo_map = []

    def count_sloc(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return sum(1 for line in f if line.strip())
        except Exception:
            return 0

    def get_deadcode_report(self):
        """Запускает deadcode, исключая лишние папки и очищая вывод от ANSI-кодов."""
        try:
            target = "app" if os.path.isdir(os.path.join(self.root_dir, "app")) else "."
            exclude_args = " ".join([f"--exclude {d}" for d in self.ignore_list])
            
            # Добавляем переменную окружения, чтобы некоторые утилиты сами отключали цвет, 
            # но основной упор сделаем на регулярку ниже.
            cmd = f'deadcode "{target}" {exclude_args}'
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                shell=True
            )
            
            output = (result.stdout or "") + (result.stderr or "")

            # --- ТОЧЕЧНОЕ ИСПРАВЛЕНИЕ: Очистка от ANSI escape-последовательностей ---
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            output = ansi_escape.sub('', output)
            # ----------------------------------------------------------------------

            if "Traceback" in output:
                return f"❌ Deadcode упал с ошибкой парсинга кода:\n{output[:500]}..."
            
            if not output.strip() or "0 unused" in output.lower():
                return "✅ Мертвого кода не обнаружено."
            
            return output.strip()
        except Exception as e:
            return f"❌ Критическая ошибка при запуске deadcode: {str(e)}"

    def extract_info(self, node):
        """Извлекает структуру (классы, методы, функции, docstrings) из AST."""
        info = {"imports": [], "skeleton": ""}
        
        for child in node.body:
            if isinstance(child, ast.Import):
                for alias in child.names:
                    info["imports"].append(f"import {alias.name}")
            elif isinstance(child, ast.ImportFrom):
                info["imports"].append(f"from {child.module or ''} import {', '.join(a.name for a in child.names)}")

            if isinstance(child, ast.ClassDef):
                doc = ast.get_docstring(child)
                doc_str = f"    # {doc.splitlines()[0]}\n" if doc else ""
                info["skeleton"] += f"\nclass {child.name}:\n{doc_str}"
                
                for item in child.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        f_doc = ast.get_docstring(item)
                        f_doc_str = f"        # {f_doc.splitlines()[0]}\n" if f_doc else ""
                        is_static = any(isinstance(d, ast.Name) and d.id == 'staticmethod' for d in item.decorator_list)
                        prefix = "    @staticmethod\n    " if is_static else "    "
                        args = ast.unparse(item.args)
                        f_type = "async def" if isinstance(item, ast.AsyncFunctionDef) else "def"
                        info["skeleton"] += f"    {prefix}{f_type} {item.name}({args}): ...\n{f_doc_str}"

            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(child)
                doc_str = f"    # {doc.splitlines()[0]}\n" if doc else ""
                args = ast.unparse(child.args)
                f_type = "async def" if isinstance(child, ast.AsyncFunctionDef) else "def"
                info["skeleton"] += f"\n{f_type} {child.name}({args}): ...\n{doc_str}"
        
        return info

    def generate_tree(self, path, tree=None):
        if tree is None:
            tree = Tree(f"📂 [bold blue]{os.path.basename(self.root_dir)}[/bold blue]")
        
        try:
            items = sorted(os.listdir(path))
        except PermissionError:
            return tree

        for item in items:
            if item in self.ignore_list:
                continue
            
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                branch = tree.add(f"📁 {item}")
                self.generate_tree(full_path, branch)
            else:
                if item.endswith(".py"):
                    tree.add(f"📄 {item}")
                elif item == "DEVELOPMENT.md":
                    tree.add(f"📝 [green]{item}[/green]")
        return tree

    def run(self):
        total_start = time.time()
        console.print(Panel.fit("[bold magenta]Project Mapper[/bold magenta]"))

        # --- ЭТАП 1: DEVELOPMENT.MD ---
        if os.path.exists("DEVELOPMENT.md"):
            with console.status("[bold green]Чтение документации..."):
                with open("DEVELOPMENT.md", "r", encoding="utf-8") as f:
                    self.repo_map.append(f"# DOCUMENTATION: DEVELOPMENT.md\n\n{f.read()}\n\n---")
            console.print("✅ [bold green]ЭТАП 1:[/bold green] DEVELOPMENT.md интегрирован.")
        else:
            console.print("ℹ️  [bold yellow]ЭТАП 1:[/bold yellow] DEVELOPMENT.md не найден. [Пропущено]")

        # --- ЭТАП 2: ДЕРЕВО ПРОЕКТА ---
        with console.status("[bold green]Сборка структуры каталогов..."):
            tree_obj = self.generate_tree(self.root_dir)
            from io import StringIO
            tree_capture = Console(file=StringIO(), force_terminal=False, width=100)
            tree_capture.print(tree_obj)
            self.repo_map.append(f"# PROJECT STRUCTURE\n\n```text\n{tree_capture.file.getvalue()}\n```\n\n---")
        console.print("✅ [bold green]ЭТАП 2:[/bold green] Визуальная структура готова.")

        # --- ЭТАП 3: DEAD CODE ---
        with console.status("[bold magenta]Запуск Dead Code Analysis (это может занять время)..."):
            report = self.get_deadcode_report()
            self.repo_map.append(f"# DEAD CODE ANALYSIS REPORT\n\n```text\n{report}\n```\n\n---")
        
        if "Мертвого кода не обнаружено" in report:
            console.print("ℹ️  [bold cyan]ЭТАП 3:[/bold cyan] Анализ завершен (проблем не найдено).")
        else:
            console.print("⚠️  [bold orange3]ЭТАП 3:[/bold orange3] Мертвый код обнаружен и внесен в отчет.")

        # --- ЭТАП 4: АНАЛИЗ ФАЙЛОВ ---
        py_files = []
        for root, dirs, files in os.walk(self.root_dir):
            dirs[:] = [d for d in dirs if d not in self.ignore_list]
            for file in files:
                if file.endswith(".py"):
                    py_files.append(os.path.join(root, file))

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True
        ) as progress:
            task = progress.add_task("[cyan]Парсинг Python файлов...", total=len(py_files))
            
            for full_path in py_files:
                rel_path = os.path.relpath(full_path, self.root_dir)
                sloc = self.count_sloc(full_path)
                header = f"## FILE: {rel_path} | SLOC: {sloc}"
                
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        
                    if rel_path in self.full_files or os.path.basename(full_path) in self.full_files:
                        self.repo_map.append(f"{header}\n\n```python\n{content}\n```\n\n---")
                    else:
                        tree = ast.parse(content)
                        data = self.extract_info(tree)
                        imports = "\n".join(data['imports'])
                        self.repo_map.append(
                            f"{header}\n\n**Imports:**\n```python\n{imports}\n```\n\n"
                            f"**Structure:**\n```python\n{data['skeleton']}\n```\n\n---"
                        )
                except Exception as e:
                    self.repo_map.append(f"{header}\n\n⚠️ Ошибка парсинга AST: {e}\n\n---")
                
                progress.advance(task)

        console.print("✅ [bold green]ЭТАП 4:[/bold green] Код проанализирован.")

        # Сохранение
        output_file = "project_map.md"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(self.repo_map))
        
        duration = round(time.time() - total_start, 2)
        console.print(Panel(
            f"✨ [bold green]Карта проекта успешно создана![/bold green]\n"
            f"🕒 Время выполнения: {duration} сек.\n"
            f"📍 Файл: [bold blue]{os.path.abspath(output_file)}[/bold blue]",
            expand=False, border_style="green"
        ))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", nargs='*', default=[], help="Файлы для полной выгрузки")
    args = parser.parse_args()
    
    # Список папок для игнорирования
    IGNORE = {'.git', '__pycache__', 'venv', '.venv', 'env', 'tests', 'dist', 'build', '.idea', '.vscode', 'node_modules'}
    
    mapper = ProjectMapper(".", IGNORE, args.full)
    mapper.run()