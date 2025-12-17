import PyInstaller.__main__
import shutil
import os

def build():
    app_name = "AvitoAssist"
    dist_dir = "dist"
    work_dir = "build"
    
    print(f"--- STARTING BUILD: {app_name} ---")
    
    # 1. Очистка
    if os.path.exists(work_dir): shutil.rmtree(work_dir)
    if os.path.exists(dist_dir): shutil.rmtree(dist_dir)
    spec_file = f"{app_name}.spec"
    if os.path.exists(spec_file): os.remove(spec_file)

    # 2. Параметры PyInstaller
    # Используем --onedir для удобства (все лежит в папке),
    # чтобы можно было легко проверить наличие backends/models.
    # Если нужен строго один файл --onefile, то backends придется добавлять через --add-data,
    # что сложнее для отладки путей. Рекомендую onedir для начала.
    
    params = [
        'main.py',
        f'--name={app_name}',
        '--onedir',                # Папка с exe и зависимостями
        '--windowed',              # БЕЗ черной консоли
        '--clean',
        '--noconfirm',
        '--paths=.',
        
        # Скрытые импорты (часто теряются)
        '--hidden-import=app.ui.styles',
        '--hidden-import=app.core.ai',
        '--hidden-import=sklearn.utils._typedefs', # Иногда нужно для sklearn
        '--hidden-import=sklearn.neighbors._partition_nodes',
        
        # Иконка (если есть, раскомментируйте)
        # '--icon=app/assets/icon.ico',
    ]

    PyInstaller.__main__.run(params)
    
    # 3. Копирование внешних ресурсов в папку dist/AvitoAssist
    # PyInstaller не захватывает DLL из папок backends автоматически, если они не прописаны как бинарники.
    # Проще скопировать папки целиком рядом с EXE.
    
    target_dir = os.path.join(dist_dir, app_name)
    
    print("\n--- Copying external resources ---")
    
    # Копируем папки
    folders_to_copy = ["backends", "models", "icons"]
    for folder in folders_to_copy:
        src = folder
        dst = os.path.join(target_dir, folder)
        if os.path.exists(src):
            print(f"Copying folder {src} -> {dst}")
            if os.path.exists(dst): shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            print(f"WARNING: Folder '{src}' not found!")

    # Копируем конкретные файлы (пресеты)
    files_to_copy = ["tag_presets.json", "tag_presets_ignore.json"]
    for filename in files_to_copy:
        if os.path.exists(filename):
            print(f"Copying file {filename} -> {target_dir}")
            shutil.copy(filename, target_dir)
        else:
            print(f"WARNING: File '{filename}' not found! Run generate_cpu_presets.py first.")

    print(f"\n--- BUILD SUCCESSFUL ---")
    print(f"Executable is located in: {target_dir}/{app_name}.exe")

if __name__ == "__main__":
    build()