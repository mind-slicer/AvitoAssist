import sys
import os
import traceback
import multiprocessing

# 1. FIX: Принудительно задаем масштабирование ДО создания QApplication
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QMessageBox
from app.ui.windows.main_window import MainWindow
from app.core.log_manager import logger

# 2. FIX: Явный импорт стилей для PyInstaller
import app.ui.styles.components
import app.ui.styles.palette
import app.ui.styles.spacing
import app.ui.styles.typography

def exception_hook(exctype, value, tb):
    # ... (код хука без изменений) ...
    error_msg = "".join(traceback.format_exception(exctype, value, tb))
    print(error_msg)
    logger.error(f"UNHANDLED EXCEPTION: {error_msg}")
    if QApplication.instance():
        QMessageBox.critical(None, "Critical Error", f"Произошла ошибка:\n{value}")
    sys.__excepthook__(exctype, value, tb)

sys.excepthook = exception_hook

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  

    # 3. FIX: Проверка загрузки стилей (для дебага в консоли)
    try:
        from app.ui.styles import Components
        app.setStyleSheet(app.ui.styles.components.Components.global_scrollbar())
        # Просто проверяем, что класс доступен, это заставит Python загрузить модуль
        print("Styles module loaded successfully.")
    except Exception as e:
        print(f"Error loading styles: {e}")

    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()