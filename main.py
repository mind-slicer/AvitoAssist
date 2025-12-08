import sys
import os
import multiprocessing

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QMessageBox
from app.ui.windows.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()