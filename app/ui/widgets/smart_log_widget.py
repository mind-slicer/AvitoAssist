from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QWidget, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from app.ui.styles import Palette, Spacing

class LogItemWidget(QWidget):
    def __init__(self, text, style, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, 2, Spacing.SM, 2)
        layout.setSpacing(Spacing.MD)

        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedWidth(24)
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.text_lbl = QLabel(text)
        self.text_lbl.setWordWrap(True)
        self.text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        
        font = QFont("Segoe UI", 9)
        self.text_lbl.setFont(font)
        self.icon_lbl.setFont(QFont("Segoe UI Emoji", 10))
        
        self.timer = None
        self._style = style

        if style == "process":
            self._init_spinner()
        else:
            self._set_static_icon(style)

        layout.addWidget(self.icon_lbl)
        layout.addWidget(self.text_lbl, 1)

    def _set_static_icon(self, style):
        color = Palette.TEXT
        icon = "🔹"
        
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
    def __init__(self):
        super().__init__()
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
        self.sticky_tokens = ["ai_batch", "ai_timer"]
        self.active_tokens = {}

    def add_log(self, token, text, style, replace):
        if token and token in self.active_tokens:
            item = self.active_tokens[token]
            widget = self.itemWidget(item)
            if widget:
                display_text = f"{text}" if token == "ai_batch" else text
                widget.set_text(display_text)
                
                if style in ["success", "error"] and widget._style == "process":
                    widget.transform_to_static(success=(style == "success"))
                return

        item = QListWidgetItem()
        widget = LogItemWidget(text, style)
        item.setSizeHint(widget.sizeHint())

        if token in self.sticky_tokens:
            self.addItem(item)
        else:
            insert_idx = self.count()
            for i in range(self.count()):
                current_item = self.item(i)
                for t, itm in self.active_tokens.items():
                    if itm == current_item and t in self.sticky_tokens:
                        insert_idx = i
                        break
                if insert_idx < self.count(): break
            
            self.insertItem(insert_idx, item)

        self.setItemWidget(item, widget)
        if token:
            self.active_tokens[token] = item
            
        self.scrollToBottom()

    def remove_log(self, token):
        if token in self.active_tokens:
            item = self.active_tokens.pop(token)
            row = self.row(item)
            if row != -1:
                self.takeItem(row)

    def clear_logs(self):
        self.clear()
        self.active_tokens.clear()