from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QWidget, QHBoxLayout, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QColor, QFont, QIcon
from app.ui.styles import Palette, Typography, Spacing

class LogItemWidget(QWidget):
    """
    Виджет одной строки лога. 
    Умеет показывать иконку или анимированный спиннер.
    """
    def __init__(self, text, style, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, 2, Spacing.SM, 2)
        layout.setSpacing(Spacing.MD)

        # Метка для иконки/спиннера (фиксированная ширина для выравнивания)
        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedWidth(24)
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Метка текста
        self.text_lbl = QLabel(text)
        self.text_lbl.setWordWrap(True)
        # Разрешаем выделение текста мышкой
        self.text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        
        # Настройка шрифтов
        font = QFont("Segoe UI", 9)
        self.text_lbl.setFont(font)
        self.icon_lbl.setFont(QFont("Segoe UI Emoji", 10)) # Для эмодзи
        
        self.timer = None
        self._style = style

        # Инициализация стиля
        if style == "process":
            self._init_spinner()
        else:
            self._set_static_icon(style)

        layout.addWidget(self.icon_lbl)
        layout.addWidget(self.text_lbl, 1) # 1 = растягиваться

    def _set_static_icon(self, style):
        color = Palette.TEXT
        icon = "🔹" # info default
        
        if style == "success":
            icon = "✨"
            color = Palette.SUCCESS
        elif style == "error":
            icon = "❌"
            color = Palette.ERROR
        elif style == "warning":
            icon = "⚠️"
            color = Palette.WARNING
        elif style == "info":
            icon = "ℹ️"
            color = "#64B5F6" # Light Blue
            
        self.icon_lbl.setText(icon)
        self.text_lbl.setStyleSheet(f"color: {color};")

    def _init_spinner(self):
        """Запуск анимации для процессов"""
        self.text_lbl.setStyleSheet(f"color: {Palette.TEXT_MUTED};")
        # Набор кадров "змейка" или точки
        self._spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._frame_idx = 0
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(80) # Скорость анимации
        self._animate()

    def _animate(self):
        self.icon_lbl.setText(self._spinner_frames[self._frame_idx])
        # Цвет спиннера - акцентный
        self.icon_lbl.setStyleSheet(f"color: {Palette.SECONDARY}; font-weight: bold; font-size: 14px;")
        self._frame_idx = (self._frame_idx + 1) % len(self._spinner_frames)

    def set_text(self, text):
        self.text_lbl.setText(text)
        
    def transform_to_static(self, success=True):
        """Превращает анимированную строку в обычную (например, когда процесс завершен)"""
        if self.timer:
            self.timer.stop()
            self.timer = None
        self._set_static_icon("success" if success else "error")
        # Возвращаем обычный цвет текста
        color = Palette.SUCCESS if success else Palette.ERROR
        self.text_lbl.setStyleSheet(f"color: {color};")

class SmartLogWidget(QListWidget):
    """
    Умный список логов.
    Поддерживает обновление строк по токенам.
    """
    def __init__(self):
        super().__init__()
        # Прозрачный фон, убираем рамки
        self.setStyleSheet(f"""
            QListWidget {{
                background: {Palette.BG_DARK_2}; 
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: 4px;
                outline: none;
            }}
            QListWidget::item {{
                border-bottom: 1px solid {Palette.BG_DARK};
            }}
            QListWidget::item:selected {{
                background: {Palette.BG_DARK_3};
            }}
        """)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.active_tokens = {} # token -> QListWidgetItem

    def add_log(self, token, text, style, replace):
        # 1. Если нужно обновить существующую строку (например, прогресс)
        if replace and token and token in self.active_tokens:
            item = self.active_tokens[token]
            widget = self.itemWidget(item)
            if widget:
                widget.set_text(text)
                # Если стиль сменился с process на success/error (финализация)
                if style in ["success", "error"] and getattr(widget, "_style", "") == "process":
                    widget.transform_to_static(success=(style == "success"))
                    # Удаляем токен, так как процесс завершен
                    del self.active_tokens[token]
            return

        # 2. Иначе добавляем новую строку
        item = QListWidgetItem()
        widget = LogItemWidget(text, style)
        
        # Важно: задаем размер элемента списка равным размеру виджета
        item.setSizeHint(widget.sizeHint())
        
        self.addItem(item)
        self.setItemWidget(item, widget)
        
        # Автоскролл вниз
        self.scrollToBottom()

        # Если у строки есть токен (это процесс), запоминаем её
        if token:
            self.active_tokens[token] = item

    def clear_logs(self):
        self.clear()
        self.active_tokens.clear()