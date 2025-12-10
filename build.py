import PyInstaller.__main__
import shutil
import os

def build():
    # 1. Название приложения
    app_name = "AvitoAssist"
    
    # 2. Очистка предыдущих сборок
    print("--- Cleaning up old builds ---")
    if os.path.exists("build"): shutil.rmtree("build")
    if os.path.exists("dist"): shutil.rmtree("dist")
    if os.path.exists(f"{app_name}.spec"): os.remove(f"{app_name}.spec")

    # 3. Параметры сборки
    # --onedir удобнее для отладки (видно все файлы), --onefile для релиза
    # Сейчас используем --onedir, чтобы видеть, если что-то не скопировалось
    
    params = [
        'main.py',                      # Основной файл
        f'--name={app_name}',           # Имя EXE
        '--onedir',                     # Пока собираем в папку (для теста) - замени на --onefile для финала
        #'--windowed',                   # Без консоли (для финала). Для отладки удали эту строку!
        '--clean',                      # Очистить кэш PyInstaller
        '--noconfirm',                  # Не спрашивать подтверждения
        
        # Включаем пути к модулям
        '--paths=.',
        
        # Скрытые импорты (PyQt6 и собственные модули иногда теряются)
        '--hidden-import=app.ui.styles',
        '--hidden-import=app.core.ai',
        
        # Добавляем данные (если есть картинки или конфиги внутри кода)
        # Формат: 'source_path;dest_path' (Windows) или 'source:dest' (Linux/Mac)
        # '--add-data=app/assets;app/assets', # Раскомментируй, если есть папка assets
    ]

    print(f"--- Building {app_name} ---")
    PyInstaller.__main__.run(params)
    print("--- Build Finished! Check /dist folder ---")

if __name__ == "__main__":
    build()