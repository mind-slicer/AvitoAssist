from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, 
                            QScrollArea, QLineEdit, QListWidgetItem, QComboBox)
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
    config_changed = pyqtSignal(dict)

    def __init__(self, cultivation_manager, parent=None):
        super().__init__(parent)
        self.manager = cultivation_manager
        
        self._updating_ui = False
        
        self.init_ui()

        if self.manager:
            # Получаем текущий конфиг через get_monitor_data
            data = self.manager.get_monitor_data()
            self._on_manager_config_updated(data.get('config', {}))
            
            # Подписываемся на изменения
            self.manager.config_updated_signal.connect(self._on_manager_config_updated)
            self.manager.pause_state_changed.connect(self._on_pause_state_changed)

        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_stats)
        self.update_timer.start(1000)

    def init_ui(self):
        self.setObjectName("CultivationMonitor")
        self.setStyleSheet(f"""
            #CultivationMonitor {{
                background-color: {Palette.BG_DARK_3};
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: {Spacing.RADIUS_SMOOTH}px;
            }}
            QLineEdit {{
                background-color: {Palette.BG_DARK_2};
                color: {Palette.TEXT};
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: 4px;
                padding: 2px 6px;
                font-family: {Typography.MONO};
            }}
            QLineEdit:focus {{ border-color: {Palette.PRIMARY}; }}
            QComboBox {{
                background-color: {Palette.BG_DARK_2};
                color: {Palette.TEXT_MUTED};
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: 4px;
                padding: 1px 4px;
                font-size: 10px;
            }}
            QComboBox::drop-down {{ border: none; }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # === 1. ЗАГОЛОВОК И СТАТУС ===
        top_layout = QHBoxLayout()
        
        self.header_label = QLabel("ПУЛЬС СИСТЕМЫ")
        self.header_label.setStyleSheet(f"color: {Palette.TEXT_SECONDARY}; font-weight: bold; font-size: 11px; letter-spacing: 1px;")
        top_layout.addWidget(self.header_label)
        top_layout.addStretch()
        
        # Индикатор следующего запуска (вместо прогресс-бара)
        self.next_run_label = QLabel("Ожидание...")
        self.next_run_label.setStyleSheet(f"color: {Palette.PRIMARY}; font-family: {Typography.MONO}; font-weight: bold;")
        top_layout.addWidget(self.next_run_label)
        
        layout.addLayout(top_layout)

        # === 2. КНОПКА ПАУЗЫ (БОЛЬШАЯ) ===
        self.btn_pause = QPushButton("⏸ ПАУЗА")
        self.btn_pause.setCheckable(True)
        self.btn_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pause.setFixedHeight(32)
        self.btn_pause.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_DARK_2};
                color: {Palette.TEXT};
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: 4px;
                font-weight: bold;
                font-size: 11px;
            }}
            QPushButton:hover {{
                border-color: {Palette.WARNING};
                color: {Palette.WARNING};
            }}
            QPushButton:checked {{
                background-color: {Palette.WARNING};
                color: #1a1a1a;
                border: 1px solid {Palette.WARNING};
            }}
        """)
        self.btn_pause.clicked.connect(self._on_pause_clicked)
        layout.addWidget(self.btn_pause)

        layout.addSpacing(4)
        
        # Разделитель
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet(f"background-color: {Palette.DIVIDER}; max-height: 1px;")
        layout.addWidget(sep1)

        # === 3. НАСТРОЙКИ (СЕТКА) ===
        # Используем сетку для выравнивания Label | Input | Unit
        
        settings_label = QLabel("ПАРАМЕТРЫ")
        settings_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-weight: bold; font-size: 9px; margin-bottom: 2px;")
        layout.addWidget(settings_label)

        # -- Poll Interval --
        self.poll_row = self._create_setting_row("Частота опроса:", "30", "poll_interval")
        layout.addLayout(self.poll_row['layout'])

        # -- Time Threshold --
        self.time_row = self._create_setting_row("Актуальность чанка:", "120", "time_threshold")
        layout.addLayout(self.time_row['layout'])

        # -- Data Threshold --
        # Тут единицы фиксированы (шт), комбобокс не нужен, но используем ту же структуру
        self.data_row = self._create_setting_row("Порог данных:", "10", "data_threshold", fixed_unit="шт")
        layout.addLayout(self.data_row['layout'])

        # -- Integrity --
        self.integrity_row = self._create_setting_row("Целостность:", "300", "integrity_interval")
        layout.addLayout(self.integrity_row['layout'])

        layout.addStretch()

        # Разделитель
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"background-color: {Palette.DIVIDER}; max-height: 1px;")
        layout.addWidget(sep2)

        # === 4. ИНФО ОЧЕРЕДИ ===
        info_layout = QHBoxLayout()
        self.queue_info = QLabel("Очередь: 0")
        self.active_info = QLabel("Активно: 0")
        
        for lbl in (self.queue_info, self.active_info):
            lbl.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 10px;")
        
        info_layout.addWidget(self.queue_info)
        info_layout.addStretch()
        info_layout.addWidget(self.active_info)
        layout.addLayout(info_layout)

    def _create_setting_row(self, label_text, default_val, config_key, fixed_unit=None):
        layout = QHBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        
        lbl = QLabel(label_text)
        lbl.setStyleSheet(f"color: {Palette.TEXT}; font-size: 11px;")
        layout.addWidget(lbl, 1) # stretch

        inp = QLineEdit(default_val)
        inp.setFixedWidth(50)
        inp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inp.editingFinished.connect(self._on_user_input_changed)
        layout.addWidget(inp)

        unit_widget = None
        if fixed_unit:
            unit_widget = QLabel(fixed_unit)
            unit_widget.setFixedWidth(45)
            unit_widget.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 10px; padding-left: 4px;")
        else:
            unit_widget = QComboBox()
            unit_widget.setFixedWidth(45)
            unit_widget.addItems(["сек", "мин"])
            unit_widget.setCursor(Qt.CursorShape.PointingHandCursor)
            # При смене единиц пересчитываем значение в поле
            unit_widget.currentIndexChanged.connect(lambda idx, i=inp: self._convert_display_value(i, idx))
            # При смене единиц также триггерим сохранение конфига
            unit_widget.currentIndexChanged.connect(self._on_user_input_changed)

        layout.addWidget(unit_widget)

        return {
            'layout': layout,
            'input': inp,
            'unit': unit_widget,
            'key': config_key,
            'fixed_unit': fixed_unit
        }

    def _convert_display_value(self, input_field: QLineEdit, new_unit_idx: int):
        """Конвертация значений в поле при смене единиц измерения"""
        if self._updating_ui: return

        try:
            val = float(input_field.text())
            if new_unit_idx == 1: # Было сек (0), стало мин (1) -> делим
                new_val = val / 60
            else: # Было мин (1), стало сек (0) -> умножаем
                new_val = val * 60
            
            if new_val.is_integer():
                input_field.setText(str(int(new_val)))
            else:
                input_field.setText(f"{new_val:.2f}".rstrip('0').rstrip('.'))
        except ValueError:
            pass
        
        self._on_user_input_changed()

    def _get_seconds_value(self, row_dict) -> int:
        """Получает значение из поля в секундах, учитывая выбранную единицу"""
        try:
            val = float(row_dict['input'].text())
            if not row_dict.get('fixed_unit') and row_dict['unit'].currentIndex() == 1: # Мин
                val *= 60
            return int(val)
        except ValueError:
            return 0

    def _set_seconds_value(self, row_dict, seconds: int):
        """Устанавливает значение в поле, конвертируя в текущую единицу"""
        is_min = (not row_dict.get('fixed_unit')) and (row_dict['unit'].currentIndex() == 1)
        val = seconds / 60 if is_min else seconds
        
        if val.is_integer():
            row_dict['input'].setText(str(int(val)))
        else:
            row_dict['input'].setText(f"{val:.1f}")

    def _on_user_input_changed(self):
        """
        Пользователь изменил значение руками.
        Считываем все поля, приводим к секундам, отправляем в менеджер.
        """
        if self._updating_ui: return

        # Читаем значения с учетом выбранных в данный момент единиц
        poll = self._read_seconds_from_row(self.poll_row)
        time_t = self._read_seconds_from_row(self.time_row)
        data_t = int(self.data_row['input'].text()) # Штуки, без конвертации
        integr = self._read_seconds_from_row(self.integrity_row)

        new_config = {
            'poll_interval': poll,
            'time_threshold': time_t,
            'data_threshold': data_t,
            'integrity_interval': integr
        }

        # Обновляем менеджер (он разошлет сигнал всем остальным виджетам)
        if self.manager:
            self.manager.update_config_full(new_config)
        
        self.config_changed.emit(new_config)
    
    def _read_seconds_from_row(self, row_dict) -> int:
        """Читает значение из поля и конвертирует в секунды, если выбраны минуты"""
        try:
            text = row_dict['input'].text().replace(',', '.')
            val = float(text)
            
            # Если есть комбобокс и выбраны минуты (индекс 1)
            if 'unit' in row_dict and isinstance(row_dict['unit'], QComboBox):
                if row_dict['unit'].currentIndex() == 1:
                    val *= 60
            
            return int(val)
        except ValueError:
            return 0

    def _on_pause_clicked(self):
        """Нажатие на кнопку Пауза"""
        is_paused = self.btn_pause.isChecked()
        if self.manager:
            self.manager.toggle_master_switch(not is_paused)

    def _on_pause_state_changed(self, enabled: bool):
        """Реакция на сигнал от менеджера (если пауза переключена из другого места)"""
        is_paused = not enabled
        if self.btn_pause.isChecked() != is_paused:
            self.btn_pause.setChecked(is_paused)
        self._update_pause_ui(is_paused)

    def _update_pause_ui(self, is_paused):
        if is_paused:
            self.btn_pause.setText("▶ ПРОДОЛЖИТЬ")
            self.header_label.setText("🛑 СИСТЕМА ОСТАНОВЛЕНА")
            self.header_label.setStyleSheet(f"color: {Palette.ERROR}; font-weight: bold; font-size: 11px; letter-spacing: 1px;")
            self.next_run_label.setText("НА ПАУЗЕ")
            self.next_run_label.setStyleSheet(f"color: {Palette.ERROR}; font-family: {Typography.MONO}; font-weight: bold;")
        else:
            self.btn_pause.setText("⏸ ПАУЗА")
            self.header_label.setText("🔄 ПУЛЬС СИСТЕМЫ")
            self.header_label.setStyleSheet(f"color: {Palette.TEXT_SECONDARY}; font-weight: bold; font-size: 11px; letter-spacing: 1px;")
            self.next_run_label.setStyleSheet(f"color: {Palette.PRIMARY}; font-family: {Typography.MONO}; font-weight: bold;")

    def _on_manager_config_updated(self, config: dict):
        """
        Сигнал от менеджера: конфиг обновился (возможно, из другого окна).
        Нужно обновить свои поля, учитывая выбранные единицы измерения.
        """
        self._updating_ui = True
        try:
            # Poll Interval
            self._set_field_value(self.poll_row, config.get('poll_interval', 30))
            # Time Threshold
            self._set_field_value(self.time_row, config.get('time_threshold', 120))
            # Data Threshold (штуки)
            self.data_row['input'].setText(str(config.get('data_threshold', 10)))
            # Integrity
            self._set_field_value(self.integrity_row, config.get('integrity_interval', 300))
        finally:
            self._updating_ui = False

    def _set_field_value(self, row_dict, seconds_value):
        """Устанавливает значение в поле, конвертируя в текущую единицу измерения виджета"""
        is_minutes = False
        if 'unit' in row_dict and isinstance(row_dict['unit'], QComboBox):
            is_minutes = (row_dict['unit'].currentIndex() == 1)
        
        val = seconds_value / 60.0 if is_minutes else float(seconds_value)
        
        # Красивое форматирование
        if val.is_integer():
            row_dict['input'].setText(str(int(val)))
        else:
            row_dict['input'].setText(f"{val:.2f}".rstrip('0').rstrip('.'))

    def update_stats(self):
        if not self.manager: return

        try:
            data = self.manager.get_monitor_data()
        except Exception:
            return

        is_paused = data.get("is_paused", False)
        
        # Обновляем состояние кнопки, если оно рассинхронизировалось
        if self.btn_pause.isChecked() != is_paused:
            self.btn_pause.blockSignals(True)
            self.btn_pause.setChecked(is_paused)
            self.btn_pause.blockSignals(False)
            self._update_pause_ui(is_paused)

        # Таймер
        if is_paused:
            self.next_run_label.setText("НА ПАУЗЕ")
        else:
            next_check = data.get("next_check", 0)
            self.next_run_label.setText(f"Опрос через: {next_check}с")

        # Очередь
        q = data.get("queue_size", 0)
        w = data.get("active_workers", 0)
        self.queue_info.setText(f"Очередь: {q}")
        self.active_info.setText(f"Обработка: {w}")
        
        if w > 0:
            self.active_info.setStyleSheet(f"color: {Palette.PRIMARY}; font-weight: bold; font-size: 10px;")
        else:
            self.active_info.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 10px;")