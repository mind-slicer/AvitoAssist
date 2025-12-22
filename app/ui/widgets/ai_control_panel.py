from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, 
                            QScrollArea, QLineEdit, QListWidget, QListWidgetItem)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from app.ui.styles import Components, Palette, Typography, Spacing

class ChatBubble(QFrame):
    def __init__(self, text: str, is_user: bool = False, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.XS)
        
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl.setStyleSheet(Typography.style(
            family=Typography.UI, size=Typography.SIZE_LG, color=Palette.TEXT)) 
        layout.addWidget(lbl)
        
        if is_user:
            bg = Palette.with_alpha(Palette.PRIMARY, 0.15) 
            border = Palette.PRIMARY
            radius_style = f"border-radius: {Spacing.RADIUS_NORMAL}px; border-bottom-right-radius: 0px;"
        else:
            bg = Palette.BG_DARK_3
            border = Palette.BORDER_SOFT
            radius_style = f"border-radius: {Spacing.RADIUS_NORMAL}px; border-bottom-left-radius: 0px;"
        
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {border};
                {radius_style}
            }}
        """)

class MonitoringItem(QFrame):
    deleted = pyqtSignal(QWidget)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QFrame {{ background-color: {Palette.BG_DARK_2}; border-radius: 4px; border: 1px solid {Palette.BORDER_SOFT}; }}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        lbl = QLabel("Мониторинг (Placeholder)")
        lbl.setStyleSheet("border: none; color: #a0a0a0;")
        layout.addWidget(lbl)
        layout.addStretch()
        btn = QPushButton("-")
        btn.setFixedSize(20, 20)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("QPushButton { color: #ff5555; background: transparent; border: 1px solid #ff5555; border-radius: 3px; font-weight: bold; } QPushButton:hover { background: #ff5555; color: white; }")
        btn.clicked.connect(lambda: self.deleted.emit(self))
        layout.addWidget(btn)

class RemovableListItem(QWidget):
    removed = pyqtSignal(QListWidgetItem)
    def __init__(self, text, item, parent=None, read_only=False, color=Palette.TEXT):
        super().__init__(parent)
        self.item = item
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8) 
        layout.setSpacing(10)
        
        if "||" in text:
            key, body = text.split("||", 1)
            display_html = f"<b>{key}</b><br><span style='color:{Palette.TEXT_MUTED}; font-size:12px;'>{body}</span>"
        else:
            display_html = text

        lbl = QLabel(display_html)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {color}; font-family: {Typography.UI}; font-size: 13px;")
        layout.addWidget(lbl, 1)

        btn_del = QPushButton("×")
        btn_del.setFixedSize(24, 24)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setStyleSheet("QPushButton { border: none; color: #666; font-size: 18px; font-weight: bold; background: transparent; } QPushButton:hover { color: #ff5555; }")
        btn_del.clicked.connect(self._on_remove)
        layout.addWidget(btn_del)

    def _on_remove(self):
        self.removed.emit(self.item)

class AIControlPanel(QWidget):
    send_message_signal = pyqtSignal(list)
    cultivate_requested = pyqtSignal()
    cultivation_finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.chat_history = []
        self.memory_manager = None
        self.init_ui()

    def set_memory_manager(self, manager):
        self.memory_manager = manager
    
    def _on_cultivate_clicked(self):
        if self.is_cultivating:
            return
        self.is_cultivating = True
        self.cultivate_requested.emit()

    def init_ui(self):
        self.setStyleSheet(f"background-color: {Palette.BG_DARK};")
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        main_layout.setSpacing(Spacing.LG)

        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        
        lbl_chat = QLabel("ЧАТ С АНАЛИТИКОМ")
        lbl_chat.setStyleSheet(Components.section_title())
        center_layout.addWidget(lbl_chat)
        
        self.chat_area = QScrollArea()
        self.chat_area.setWidgetResizable(True)
        self.chat_area.setStyleSheet(Components.scroll_area())
        
        self.chat_container = QWidget()
        self.chat_vbox = QVBoxLayout(self.chat_container)
        
        self.chat_vbox.addStretch() 
        self.chat_vbox.setSpacing(10)
        
        self.chat_area.setWidget(self.chat_container)
        center_layout.addWidget(self.chat_area)
        
        input_layout = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Спроси про цены, рынок или совет...")
        self.chat_input.setStyleSheet(Components.text_input())
        self.chat_input.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.chat_input)
        
        self.btn_send = QPushButton("➤")
        self.btn_send.setFixedSize(40, 32)
        self.btn_send.setStyleSheet(Components.small_button())
        self.btn_send.clicked.connect(self.send_message)
        input_layout.addWidget(self.btn_send)
        
        center_layout.addLayout(input_layout)
        main_layout.addWidget(center_widget, 1)

    def send_message(self):
        text = self.chat_input.text().strip()
        if not text: return
        self.chat_input.clear()

        self.add_bubble(text, is_user=True)
        self.chat_history.append({"role": "user", "content": text})

        self.send_message_signal.emit(self.chat_history)

        if hasattr(self, 'typing_lbl') and self.typing_lbl:
            self.typing_lbl.deleteLater()
            
        self.typing_lbl = QLabel("AI печатает...")
        self.typing_lbl.setStyleSheet("color: #808080; font-style: italic; margin-left: 10px; margin-bottom: 5px;")
        
        self.chat_vbox.addWidget(self.typing_lbl)
        self.scroll_down()

    def on_ai_reply(self, text: str):
        if hasattr(self, 'typing_lbl') and self.typing_lbl:
            self.typing_lbl.deleteLater()
            self.typing_lbl = None
            
        self.add_bubble(text, is_user=False)
        self.chat_history.append({"role": "assistant", "content": text})

    def add_bubble(self, text, is_user):
        bubble = ChatBubble(text, is_user)
        h = QHBoxLayout()
        
        if is_user:
            h.addStretch()
            h.addWidget(bubble)
        else:
            h.addWidget(bubble)
            h.addStretch()
            
        self.chat_vbox.addLayout(h)
        self.scroll_down()

    def scroll_down(self):
        if self.chat_area and self.chat_area.verticalScrollBar():
            QTimer.singleShot(100, lambda: self.chat_area.verticalScrollBar().setValue(
                self.chat_area.verticalScrollBar().maximum()))