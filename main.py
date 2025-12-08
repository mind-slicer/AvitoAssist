import sys
import os
import traceback
import multiprocessing

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QMessageBox
from app.ui.windows.main_window import MainWindow
from app.core.log_manager import logger

def exception_hook(exctype, value, tb):
    error_msg = "".join(traceback.format_exception(exctype, value, tb))
    print(error_msg) # В консоль IDE
    logger.error(f"UNHANDLED EXCEPTION: {error_msg}")
    
    # Показываем окно пользователю (если GUI еще жив)
    if QApplication.instance():
        QMessageBox.critical(None, "Critical Error", f"Произошла критическая ошибка:\n{value}")
    
    # Вызываем старый хук
    sys.__excepthook__(exctype, value, tb)

# Устанавливаем хук
sys.excepthook = exception_hook

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()