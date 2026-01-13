from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, 
                            QScrollArea, QLineEdit, QListWidgetItem, QProgressBar)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from app.ui.styles import Components, Palette, Typography, Spacing
from app.core.log_manager import logger

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

        btn_del = QPushButton("X")
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
            

class CultivationMonitorWidget(QFrame):
    config_changed = pyqtSignal(dict)  # Все настройки одним словарем
    
    def __init__(self, cultivation_manager, parent=None):
        super().__init__(parent)
        self.manager = cultivation_manager
        self.init_ui()
        
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_stats)
        self.update_timer.start(1000)
    
    def init_ui(self):
        self.setObjectName("CultivationMonitor")
        self.setMinimumHeight(220)  # Увеличили высоту
        self.setStyleSheet(f"""
            #CultivationMonitor {{
                background-color: {Palette.BG_DARK_3};
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: {Spacing.RADIUS_SMOOTH}px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Заголовок
        header = QLabel("🔄 ПУЛЬС СИСТЕМЫ")
        header.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-weight: bold; font-size: 10px; letter-spacing: 1px;")
        layout.addWidget(header)
        
        # 1. Главный опрос (прогресс-бар)
        poll_layout = QHBoxLayout()
        poll_layout.setSpacing(6)
        
        poll_label = QLabel("Опрос:")
        poll_label.setStyleSheet(f"color: {Palette.TEXT}; font-size: 11px;")
        poll_layout.addWidget(poll_label)
        
        self.pb = QProgressBar()
        self.pb.setFixedHeight(6)
        self.pb.setTextVisible(False)
        self.pb.setRange(0, 30)  # Будет динамически обновляться
        self.pb.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Palette.BG_DARK_2};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: {Palette.PRIMARY};
                border-radius: 3px;
            }}
        """)
        poll_layout.addWidget(self.pb, 1)
        
        self.poll_time_label = QLabel("—")
        self.poll_time_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 10px; min-width: 25px;")
        poll_layout.addWidget(self.poll_time_label)
        
        layout.addLayout(poll_layout)
        
        # 2. Ближайшее обновление (TIME_ELAPSED)
        self.nearest_label = QLabel("⏱️ Расчет...")
        self.nearest_label.setStyleSheet(f"color: {Palette.TEXT}; font-size: 11px;")
        self.nearest_label.setWordWrap(True)
        layout.addWidget(self.nearest_label)
        
        # 3. Аномалии цен (MARKET_DEVIATION)
        self.deviation_label = QLabel("📊 Отслеживание цен...")
        self.deviation_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 10px;")
        self.deviation_label.setWordWrap(True)
        layout.addWidget(self.deviation_label)
        
        # Разделитель
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet(f"background-color: {Palette.BORDER_SOFT}; max-height: 1px;")
        layout.addWidget(separator)
        
        # 4. НАСТРОЙКИ (редактируемые поля)
        settings_label = QLabel("⚙️ НАСТРОЙКИ")
        settings_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-weight: bold; font-size: 9px; letter-spacing: 1px; margin-top: 2px;")
        layout.addWidget(settings_label)
        
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(4)
        
        # 4.1 Частота опроса (_cultivation_timer)
        poll_interval_layout = QHBoxLayout()
        poll_interval_layout.setSpacing(6)
        
        poll_interval_label = QLabel("Частота опроса:")
        poll_interval_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 10px;")
        poll_interval_layout.addWidget(poll_interval_label)
        
        self.poll_interval_input = QLineEdit()
        self.poll_interval_input.setFixedWidth(50)
        self.poll_interval_input.setText("30")
        self.poll_interval_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poll_interval_input.setStyleSheet(self._input_style())
        self.poll_interval_input.editingFinished.connect(self._on_config_changed)
        poll_interval_layout.addWidget(self.poll_interval_input)
        
        poll_suffix = QLabel("сек")
        poll_suffix.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 10px;")
        poll_interval_layout.addWidget(poll_suffix)
        poll_interval_layout.addStretch()
        
        settings_layout.addLayout(poll_interval_layout)
        
        # 4.2 Срок актуальности чанка (default_time_threshold)
        time_layout = QHBoxLayout()
        time_layout.setSpacing(6)
        
        time_label = QLabel("Срок актуальности:")
        time_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 10px;")
        time_label.setToolTip("Минимальное время между обновлениями одного чанка")
        time_layout.addWidget(time_label)
        
        self.time_input = QLineEdit()
        self.time_input.setFixedWidth(50)
        self.time_input.setText("120")
        self.time_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_input.setStyleSheet(self._input_style())
        self.time_input.editingFinished.connect(self._on_config_changed)
        time_layout.addWidget(self.time_input)
        
        time_suffix = QLabel("сек")
        time_suffix.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 10px;")
        time_layout.addWidget(time_suffix)
        time_layout.addStretch()
        
        settings_layout.addLayout(time_layout)
        
        # 4.3 Порог новых данных (default_data_threshold)
        data_layout = QHBoxLayout()
        data_layout.setSpacing(6)
        
        data_label = QLabel("Порог новых данных:")
        data_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 10px;")
        data_label.setToolTip("Количество новых записей для принудительного обновления")
        data_layout.addWidget(data_label)
        
        self.data_input = QLineEdit()
        self.data_input.setFixedWidth(50)
        self.data_input.setText("10")
        self.data_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.data_input.setStyleSheet(self._input_style())
        self.data_input.editingFinished.connect(self._on_config_changed)
        data_layout.addWidget(self.data_input)
        
        data_suffix = QLabel("шт")
        data_suffix.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 10px;")
        data_layout.addWidget(data_suffix)
        data_layout.addStretch()
        
        settings_layout.addLayout(data_layout)
        
        # 4.4 Проверка целостности (_integrity_timer)
        integrity_layout = QHBoxLayout()
        integrity_layout.setSpacing(6)
        
        integrity_label = QLabel("Проверка целостности:")
        integrity_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 10px;")
        integrity_label.setToolTip("Частота проверки изменений сырых данных (хеш-сумм)")
        integrity_layout.addWidget(integrity_label)
        
        self.integrity_input = QLineEdit()
        self.integrity_input.setFixedWidth(50)
        self.integrity_input.setText("300")
        self.integrity_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.integrity_input.setStyleSheet(self._input_style())
        self.integrity_input.editingFinished.connect(self._on_config_changed)
        integrity_layout.addWidget(self.integrity_input)
        
        integrity_suffix = QLabel("сек")
        integrity_suffix.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 10px;")
        integrity_layout.addWidget(integrity_suffix)
        integrity_layout.addStretch()
        
        settings_layout.addLayout(integrity_layout)
        
        layout.addLayout(settings_layout)
        
        # 5. Очередь
        self.queue_label = QLabel("Очередь: — / Активно: —")
        self.queue_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 10px;")
        layout.addWidget(self.queue_label)
    
    def _input_style(self):
        return f"""
            QLineEdit {{
                background-color: {Palette.BG_DARK_2};
                color: {Palette.TEXT};
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: 3px;
                padding: 2px 4px;
                font-size: 10px;
            }}
            QLineEdit:focus {{
                border-color: {Palette.PRIMARY};
            }}
        """
    
    def _on_config_changed(self):
        """Обработка изменения настроек"""
        try:
            poll_interval = int(self.poll_interval_input.text())
            time_val = int(self.time_input.text())
            data_val = int(self.data_input.text())
            integrity_val = int(self.integrity_input.text())
            
            # Валидация
            poll_interval = max(10, min(300, poll_interval))   # 10 сек - 5 минут
            time_val = max(30, min(3600, time_val))            # 30 сек - 1 час
            data_val = max(1, min(100, data_val))              # 1-100 элементов
            integrity_val = max(60, min(3600, integrity_val))  # 1 мин - 1 час
            
            # Обновляем поля (на случай коррекции)
            self.poll_interval_input.setText(str(poll_interval))
            self.time_input.setText(str(time_val))
            self.data_input.setText(str(data_val))
            self.integrity_input.setText(str(integrity_val))
            
            # Применяем в менеджере
            if self.manager:
                self.manager.update_config_full({
                    'poll_interval': poll_interval,
                    'time_threshold': time_val,
                    'data_threshold': data_val,
                    'integrity_interval': integrity_val
                })
                logger.info(
                    f"⚙️ Настройки: Опрос={poll_interval}с, Актуальность={time_val}с, "
                    f"Данные={data_val}шт, Целостность={integrity_val}с",
                    token="ai-conf"
                )
            
            self.config_changed.emit({
                'poll_interval': poll_interval,
                'time_threshold': time_val,
                'data_threshold': data_val,
                'integrity_interval': integrity_val
            })
            
        except ValueError:
            # Возвращаем значения по умолчанию
            self.poll_interval_input.setText("30")
            self.time_input.setText("120")
            self.data_input.setText("10")
            self.integrity_input.setText("300")
    
    def update_stats(self):
        if not self.manager:
            return
        
        try:
            data = self.manager.get_monitor_data()
        except AttributeError:
            return
        
        # Главный опрос (обновляем max range динамически)
        poll_interval = data.get("config", {}).get("poll_interval", 30)
        next_check = data.get("next_check", 0)
        
        self.pb.setRange(0, poll_interval)
        self.pb.setValue(poll_interval - next_check)
        self.poll_time_label.setText(f"{next_check}с")
        
        # Ближайшее TIME_ELAPSED обновление
        nearest = data.get("nearest_time_trigger")
        if nearest:
            title = nearest["chunk_title"][:25]
            secs = nearest["seconds_left"]
            mins = secs // 60
            if mins > 0:
                time_str = f"{mins}м {secs % 60}с"
            else:
                time_str = f"{secs}с"
            self.nearest_label.setText(f"⏱️ '{title}' через {time_str}")
            self.nearest_label.setStyleSheet(f"color: {Palette.TEXT}; font-size: 11px; font-weight: bold;")
        else:
            self.nearest_label.setText("⏱️ Все чанки свежие")
            self.nearest_label.setStyleSheet(f"color: {Palette.SUCCESS}; font-size: 11px;")
        
        # Аномалии цен
        deviations = data.get("pending_market_deviations", [])
        if deviations:
            top = deviations[0]
            percent = top["deviation_percent"]
            title = top["chunk_title"][:20]
            icon = "📉" if percent < 0 else "📈"
            color = Palette.SUCCESS if percent < 0 else Palette.WARNING
            
            self.deviation_label.setText(
                f"{icon} '{title}': {percent:+.1f}% "
                f"({top['stored_avg']}₽→{top['current_avg']}₽)"
            )
            self.deviation_label.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: bold;")
        else:
            self.deviation_label.setText("📊 Цены стабильны")
            self.deviation_label.setStyleSheet(f"color: {Palette.SUCCESS}; font-size: 10px;")
        
        # Очередь
        q = data.get("queue_size", 0)
        w = data.get("active_workers", 0)
        is_cult = data.get("is_cultivating", False)
        
        if is_cult:
            self.queue_label.setText(f"⚙️ Обработка... | Очередь: {q}")
            self.queue_label.setStyleSheet(f"color: {Palette.PRIMARY}; font-size: 10px; font-weight: bold;")
        else:
            self.queue_label.setText(f"Очередь: {q} / Активно: {w}")
            self.queue_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 10px;")
        
        # Синхронизируем поля настроек из конфига
        config = data.get("config", {})
        self._sync_field(self.poll_interval_input, config.get("poll_interval", 30))
        self._sync_field(self.time_input, config.get("time_threshold", 120))
        self._sync_field(self.data_input, config.get("data_threshold", 10))
        self._sync_field(self.integrity_input, config.get("integrity_interval", 300))
    
    def _sync_field(self, field: QLineEdit, value: int):
        """Синхронизирует поле с конфигом (если не в фокусе)"""
        if not field.hasFocus() and field.text() != str(value):
            field.setText(str(value))