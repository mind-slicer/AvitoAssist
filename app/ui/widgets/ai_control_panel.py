from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                           QComboBox, QSlider, QTextEdit, QFrame, QPushButton, 
                           QScrollArea, QLineEdit, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from app.ui.styles import Components, Palette, Typography, Spacing

class ChatBubble(QFrame):
    def __init__(self, text: str, is_user: bool = False, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)
        layout.setSpacing(Spacing.XS)
        
        if not is_user:
            name = QLabel("AI Assistant")
            name.setStyleSheet(Typography.style(
                family=Typography.UI, size=Typography.SIZE_SM, weight=Typography.WEIGHT_SEMIBOLD, color=Palette.SECONDARY))
            layout.addWidget(name)
            
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl.setStyleSheet(Typography.style(
            family=Typography.UI, size=Typography.SIZE_MD, color=Palette.TEXT))
        layout.addWidget(lbl)
        
        bg = Palette.BG_DARK_3 if is_user else Palette.BG_DARK_2
        border = Palette.BORDER_SOFT if is_user else Palette.SECONDARY
        
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: {Spacing.RADIUS_NORMAL}px;
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

class AIControlPanel(QWidget):
    send_message_signal = pyqtSignal(list) # Сигнал для отправки сообщения в контроллер

    def __init__(self, parent=None):
        super().__init__(parent)
        self.chat_history = [] # Храним историю сообщений
        self.init_ui()
        
    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        main_layout.setSpacing(Spacing.LG)

        # --- LEFT COLUMN: Settings & Monitor ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(Spacing.MD)

        # 1. Strategy
        lbl_strat = QLabel("Стратегия (Persona)")
        lbl_strat.setStyleSheet(Components.section_title())
        left_layout.addWidget(lbl_strat)
        
        self.combo_persona = QComboBox()
        self.combo_persona.addItems(["💰 Перекуп", "💎 Качество", "🦄 Коллекционер"])
        self.combo_persona.setStyleSheet(Components.styled_combobox())
        left_layout.addWidget(self.combo_persona)
        
        # 2. Strictness
        strict_h = QHBoxLayout()
        self.lbl_strict_val = QLabel("Средний")
        self.lbl_strict_val.setStyleSheet(f"color: {Palette.SECONDARY}; font-weight: bold;")
        strict_h.addWidget(QLabel("Строгость:"))
        strict_h.addWidget(self.lbl_strict_val)
        strict_h.addStretch()
        left_layout.addLayout(strict_h)
        
        self.slider_strict = QSlider(Qt.Orientation.Horizontal)
        self.slider_strict.setRange(1, 5)
        self.slider_strict.setValue(3)
        self.slider_strict.valueChanged.connect(self.on_slider_change)
        left_layout.addWidget(self.slider_strict)

        # 3. Monitor
        lbl_mon = QLabel("Мониторинг")
        lbl_mon.setStyleSheet(Components.section_title())
        mon_header = QHBoxLayout()
        mon_header.addWidget(lbl_mon)
        mon_header.addStretch()
        self.btn_add_mon = QPushButton("+")
        self.btn_add_mon.setFixedSize(24, 24)
        self.btn_add_mon.setStyleSheet(Components.small_button())
        self.btn_add_mon.clicked.connect(self.add_monitor_item)
        mon_header.addWidget(self.btn_add_mon)
        left_layout.addLayout(mon_header)
        
        self.mon_scroll = QScrollArea()
        self.mon_scroll.setWidgetResizable(True)
        self.mon_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.mon_container = QWidget()
        self.mon_vbox = QVBoxLayout(self.mon_container)
        self.mon_vbox.setContentsMargins(0,0,0,0)
        self.mon_vbox.addStretch()
        self.mon_scroll.setWidget(self.mon_container)
        left_layout.addWidget(self.mon_scroll)
        
        left_widget.setFixedWidth(280) # Фиксированная ширина настроек
        main_layout.addWidget(left_widget)

        # --- RIGHT COLUMN: Chat & Instructions ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(Spacing.SM)
        
        lbl_chat = QLabel("Чат с Аналитиком")
        lbl_chat.setStyleSheet(Components.section_title())
        right_layout.addWidget(lbl_chat)
        
        # Chat Area
        self.chat_area = QScrollArea()
        self.chat_area.setWidgetResizable(True)
        self.chat_area.setStyleSheet(f"""
            QScrollArea {{ background-color: {Palette.BG_DARK_2}; border: 1px solid {Palette.BORDER_SOFT}; border-radius: {Spacing.RADIUS_NORMAL}px; }}
        """)
        self.chat_container = QWidget()
        self.chat_vbox = QVBoxLayout(self.chat_container)
        self.chat_vbox.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        self.chat_vbox.setSpacing(Spacing.MD)
        self.chat_vbox.addStretch()
        self.chat_area.setWidget(self.chat_container)
        right_layout.addWidget(self.chat_area, 1) # Растягиваем чат
        
        # Input Area
        input_layout = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Спроси про рынок или дай инструкцию...")
        self.chat_input.setStyleSheet(Components.text_input())
        self.chat_input.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.chat_input)
        
        self.btn_send = QPushButton("➤")
        self.btn_send.setFixedSize(40, 32)
        self.btn_send.setStyleSheet(Components.small_button())
        self.btn_send.clicked.connect(self.send_message)
        input_layout.addWidget(self.btn_send)
        
        right_layout.addLayout(input_layout)
        
        # System Prompt (Optional override)
        lbl_sys = QLabel("Системный промпт (дополнительно):")
        lbl_sys.setStyleSheet("color: #808080; font-size: 11px; margin-top: 5px;")
        right_layout.addWidget(lbl_sys)
        
        self.text_instructions = QTextEdit()
        self.text_instructions.setPlaceholderText("Особые условия для AI...")
        self.text_instructions.setMaximumHeight(50)
        self.text_instructions.setStyleSheet(f"background: {Palette.BG_DARK_2}; border: 1px solid {Palette.BORDER_SOFT}; color: {Palette.TEXT}; border-radius: 4px;")
        right_layout.addWidget(self.text_instructions)

        main_layout.addWidget(right_widget, 1)

    def on_slider_change(self, val):
        labels = {1: "Пофигист", 2: "Мягкий", 3: "Средний", 4: "Строгий", 5: "Параноик"}
        self.lbl_strict_val.setText(labels.get(val, "Средний"))

    def add_monitor_item(self):
        item = MonitoringItem()
        item.deleted.connect(self.remove_monitor_item)
        self.mon_vbox.insertWidget(0, item)
    
    def remove_monitor_item(self, widget):
        widget.deleteLater()

    def send_message(self):
        text = self.chat_input.text().strip()
        if not text: return
        self.chat_input.clear()
        
        # Добавляем сообщение юзера
        self.add_bubble(text, is_user=True)
        self.chat_history.append({"role": "user", "content": text})
        
        # Эмитим сигнал (в контроллер)
        # ВАЖНО: Мы тут должны передать историю + промпт.
        # Пока передаем просто список сообщений для ChatCompletion
        self.send_message_signal.emit(self.chat_history)
        
        # Показываем "печатает..."
        self.typing_lbl = QLabel("AI печатает...")
        self.typing_lbl.setStyleSheet("color: #808080; font-style: italic;")
        self.chat_vbox.addWidget(self.typing_lbl)
        self.scroll_down()

    def on_ai_reply(self, text: str):
        if hasattr(self, 'typing_lbl'):
            self.typing_lbl.deleteLater()
            del self.typing_lbl
            
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
        self.chat_vbox.insertLayout(self.chat_vbox.count()-1, h)
        if hasattr(self, 'typing_lbl'): # Если typing был последним, переставим его в конец
             self.chat_vbox.removeWidget(self.typing_lbl)
             self.chat_vbox.addWidget(self.typing_lbl)
             
        self.scroll_down()

    def scroll_down(self):
        QTimer.singleShot(100, lambda: self.chat_area.verticalScrollBar().setValue(
            self.chat_area.verticalScrollBar().maximum()))