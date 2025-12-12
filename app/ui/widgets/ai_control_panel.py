from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                           QComboBox, QSlider, QTextEdit, QFrame, QPushButton, 
                           QScrollArea, QLineEdit, QSizePolicy, QListWidget, QListWidgetItem)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
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
            # USER: Справа, зеленый оттенок (или темный), хвостик справа внизу
            bg = Palette.with_alpha(Palette.PRIMARY, 0.15) 
            border = Palette.PRIMARY
            # Скругляем все, кроме правого нижнего (или верхнего правого)
            radius_style = f"border-radius: {Spacing.RADIUS_NORMAL}px; border-bottom-right-radius: 0px;"
        else:
            # AI: Слева, серый, хвостик слева внизу
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
        
        # Ключ (жирный) и текст (обычный) для знаний
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
    send_message_signal = pyqtSignal(list, list)
    cultivate_requested = pyqtSignal()
    cultivation_finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.chat_history = []
        self.memory_manager = None
        self.init_ui()
         
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_knowledge_list)
        self.refresh_timer.start(5000)

    def set_memory_manager(self, manager):
        self.memory_manager = manager
        self._refresh_knowledge_list()
    
    def _on_cultivate_clicked(self):
        if self.is_cultivating:
            return
        self.is_cultivating = True
        self.btn_cultivate.setEnabled(False)
        self.btn_cultivate.setText("Анализ...")
        self.cultivate_requested.emit()
        # Подключаем сигнал завершения культивации для разблокировки кнопки
        self.cultivation_finished.connect(self._reset_cultivate_button)
    
    def _reset_cultivate_button(self):
        self.is_cultivating = False
        self.btn_cultivate.setEnabled(True)
        self.btn_cultivate.setText("🧠 Анализ рынка")

    def init_ui(self):
        self.setStyleSheet(f"background-color: {Palette.BG_DARK};")
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        main_layout.setSpacing(Spacing.LG)
        
        # Состояние кнопки для предотвращения многократных нажатий
        self.is_cultivating = False

        # --- КОЛОНКА 1: ИНСТРУКЦИИ (User Input) ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(Spacing.MD)

        instr_group = QFrame()
        instr_group.setStyleSheet(Components.panel())
        instr_vbox = QVBoxLayout(instr_group)
        
        instr_lbl = QLabel("Инструкции")
        instr_lbl.setToolTip("Жесткие правила поведения для ИИ (System Prompt).")
        instr_lbl.setStyleSheet(Components.subsection_title())
        instr_vbox.addWidget(instr_lbl)

        self.instr_list = QListWidget()
        self.instr_list.setStyleSheet(Components.styled_list_widget())
        instr_vbox.addWidget(self.instr_list)
        
        self.new_instr_edit = QLineEdit()
        self.new_instr_edit.setPlaceholderText("Пример: Будь краток...")
        self.new_instr_edit.setStyleSheet(Components.text_input())
        self.new_instr_edit.returnPressed.connect(self.add_instruction_from_edit)
        instr_vbox.addWidget(self.new_instr_edit)
        
        left_layout.addWidget(instr_group)
        left_widget.setFixedWidth(280)
        main_layout.addWidget(left_widget)

        # --- КОЛОНКА 2: ЧАТ (Center) ---
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
        
        # ВАЖНО: Пружина добавляется ПЕРВОЙ. Она давит сверху вниз.
        self.chat_vbox.addStretch() 
        self.chat_vbox.setSpacing(10) # Комфортный отступ между сообщениями
        
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

        # --- КОЛОНКА 3: ЗНАНИЯ (RAG Output) ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        know_group = QFrame()
        know_group.setStyleSheet(Components.panel())
        know_vbox = QVBoxLayout(know_group)
        
        know_lbl = QLabel("ПАМЯТЬ ИИ")
        know_lbl.setToolTip("Выводы, которые ИИ сделал сам. Удалите, если не согласны.")
        know_lbl.setStyleSheet(Components.subsection_title())
        know_vbox.addWidget(know_lbl)
        
        self.knowledge_list = QListWidget()
        self.knowledge_list.setStyleSheet(Components.styled_list_widget())
        know_vbox.addWidget(self.knowledge_list)
        
        btns_layout = QHBoxLayout()
        self.btn_cultivate = QPushButton("🧠 Анализ рынка")
        self.btn_cultivate.setToolTip("Запустить ИИ для анализа накопленных данных")
        self.btn_cultivate.setStyleSheet(Components.small_button())
        self.btn_cultivate.clicked.connect(self._on_cultivate_clicked)
        
        self.btn_refresh = QPushButton("⟳")
        self.btn_refresh.setFixedSize(32, 28)
        self.btn_refresh.setStyleSheet(Components.small_button())
        self.btn_refresh.clicked.connect(self._refresh_knowledge_list)
        
        btns_layout.addWidget(self.btn_cultivate)
        btns_layout.addWidget(self.btn_refresh)
        know_vbox.addLayout(btns_layout)

        right_layout.addWidget(know_group)
        right_widget.setFixedWidth(280)
        main_layout.addWidget(right_widget)

    # --- Logic ---

    def add_instruction_from_edit(self):
        text = self.new_instr_edit.text().strip()
        if not text: return
        self.new_instr_edit.clear()
        item = QListWidgetItem(self.instr_list)
        widget = RemovableListItem(text, item, self, color=Palette.SUCCESS)
        widget.removed.connect(self.remove_instruction)
        item.setSizeHint(widget.sizeHint())
        self.instr_list.addItem(item)
        self.instr_list.setItemWidget(item, widget)

    def remove_instruction(self, item):
        row = self.instr_list.row(item)
        self.instr_list.takeItem(row)

    def _refresh_knowledge_list(self):
        if not self.memory_manager: return
        try:
            knowledge = self.memory_manager.get_all_knowledge_summaries()
            self.knowledge_list.clear()
            for k in knowledge:
                key = k['product_key']
                summary = k['summary']
                full_text = f"{key}||{summary}"
                
                item = QListWidgetItem(self.knowledge_list)
                widget = RemovableListItem(full_text, item, self, color=Palette.TERTIARY)
                widget.removed.connect(lambda i, ky=key: self.remove_knowledge(i, ky))
                
                item.setSizeHint(widget.sizeHint())
                self.knowledge_list.addItem(item)
                self.knowledge_list.setItemWidget(item, widget)
        except: pass

    def remove_knowledge(self, item, key):
        if self.memory_manager:
            self.memory_manager.delete_knowledge(key)
        row = self.knowledge_list.row(item)
        self.knowledge_list.takeItem(row)

    def send_message(self):
        text = self.chat_input.text().strip()
        if not text: return
        self.chat_input.clear()
        
        # 1. Добавляем сообщение пользователя
        self.add_bubble(text, is_user=True)
        self.chat_history.append({"role": "user", "content": text})
        
        # 2. Собираем инструкции
        current_instr = []
        for i in range(self.instr_list.count()):
            it = self.instr_list.item(i)
            wdg = self.instr_list.itemWidget(it)
            if wdg:
                lbs = wdg.findChildren(QLabel)
                if lbs: current_instr.append(lbs[0].text())
        
        # 3. Отправляем сигнал
        self.send_message_signal.emit(self.chat_history, current_instr)
        
        # 4. Показываем индикатор печати (удаляем старый, если вдруг завис)
        if hasattr(self, 'typing_lbl') and self.typing_lbl:
            self.typing_lbl.deleteLater()
            
        self.typing_lbl = QLabel("AI печатает...")
        self.typing_lbl.setStyleSheet("color: #808080; font-style: italic; margin-left: 10px; margin-bottom: 5px;")
        
        # Добавляем в самый низ
        self.chat_vbox.addWidget(self.typing_lbl)
        self.scroll_down()

    def on_ai_reply(self, text: str):
        # Удаляем индикатор печати
        if hasattr(self, 'typing_lbl') and self.typing_lbl:
            self.typing_lbl.deleteLater()
            self.typing_lbl = None
            
        self.add_bubble(text, is_user=False)
        self.chat_history.append({"role": "assistant", "content": text})

    def add_bubble(self, text, is_user):
        bubble = ChatBubble(text, is_user)
        h = QHBoxLayout()
        
        if is_user:
            # USER -> СПРАВА
            h.addStretch()
            h.addWidget(bubble)
        else:
            # AI -> СЛЕВА
            h.addWidget(bubble)
            h.addStretch()
            
        # Просто добавляем в конец лейаута (после всех сообщений и пружины)
        self.chat_vbox.addLayout(h)
        self.scroll_down()

    def scroll_down(self):
        if self.chat_area and self.chat_area.verticalScrollBar():
            QTimer.singleShot(100, lambda: self.chat_area.verticalScrollBar().setValue(
                self.chat_area.verticalScrollBar().maximum()))