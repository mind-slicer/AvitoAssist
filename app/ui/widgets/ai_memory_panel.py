import json
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QToolTip, QLineEdit,
    QTextEdit, QSizePolicy, QTabWidget, QPlainTextEdit, QCheckBox,
    QComboBox, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent
from PyQt6.QtGui import QTextOption

from app.ui.styles import Components, Palette, Spacing, Typography
from app.core.log_manager import logger
from app.core.ai.prompts import prompt_manager
from app.config import BASE_APP_DIR


# Default main points of interest
DEFAULT_INTERESTS_TEXT = """
=== СПИСОК ИНТЕРЕСУЮЩЕГО ЖЕЛЕЗА ===
1. ВИДЕОКАРТЫ:
- Nvidia: RTX 50/40/30/20 серии, GTX 16xx/10xx серии.
- AMD: RX 9000/7000/6000/5000/500/400 серии.
2. ПРОЦЕССОРЫ:
- Intel: LGA 1851/1700/1200/1151(v1/v2)/1150/1155. Поколения: с 2-го по 15-е.
- AMD: AM5, AM4. Ryzen 1000-9000 серии.
3. МАТЕРИНСКИЕ ПЛАТЫ: все чипсеты под указанные выше сокеты.
4. ОПЕРАТИВНАЯ ПАМЯТЬ:
- DDR5.
- DDR4 (частоты 2133-4000+).
5. НАКОПИТЕЛИ: NVMe M.2, SATA SSD (от 60gb до 1tb+), HDD (от 1tb).
6. БЛОКИ ПИТАНИЯ: От 500W до 1000W+.
7. ОХЛАЖДЕНИЕ: Башенные кулеры, СВО/СЖО (водяное/жидкостное охлаждение, водянка).
8. ДРУГОЕ: Готовые сборки ПК, мониторы, ноутбуки, корпуса.
"""


class ChunkCard(QFrame):    
    deleted = pyqtSignal(int)
    refresh_requested = pyqtSignal(int)
    
    def __init__(self, chunk_data: dict, parent=None):
        super().__init__(parent)
        self.chunk_data = chunk_data
        self.chunk_id = chunk_data.get('id')
        self.status = chunk_data.get('status')
        
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Palette.BG_LIGHT};
                border: 1px solid {Palette.BORDER_PRIMARY};
                border-radius: 8px;
            }}
        """)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        
        self._init_ui()
        self._update_appearance()
    
    def _init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 12, 12, 12)
        self.layout.setSpacing(8)
        
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(24, 24)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("font-size: 16px; border: none; background: transparent;")
        header_layout.addWidget(self.icon_label)
        
        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)
        
        self.title_label = QLabel()
        self.title_label.setStyleSheet(f"font-weight: bold; color: {Palette.TEXT}; font-size: 13px; border: none;")
        self.title_label.setWordWrap(True)
        title_layout.addWidget(self.title_label)
        
        self.status_label = QLabel()
        self.status_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 11px; border: none;")
        title_layout.addWidget(self.status_label)
        
        header_layout.addLayout(title_layout, stretch=1)
        
        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setFixedSize(24, 24)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setToolTip("Отправить на перегенерацию") 
        self.refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {Palette.BORDER_SOFT};
                color: {Palette.PRIMARY};
                border-radius: 4px;
                font-weight: bold;
                padding-bottom: 2px;
            }}
            QPushButton:hover {{
                background: {Palette.with_alpha(Palette.PRIMARY, 0.1)};
                border-color: {Palette.PRIMARY};
            }}
        """)
        self.refresh_btn.clicked.connect(self._on_refresh)
        header_layout.addWidget(self.refresh_btn)

        self.delete_btn = QPushButton("✕")
        self.delete_btn.setFixedSize(24, 24)
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {Palette.TEXT_MUTED};
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {Palette.ERROR};
                background: rgba(255, 0, 0, 0.1);
                border-radius: 4px;
            }}
        """)
        self.delete_btn.clicked.connect(self._on_delete)
        header_layout.addWidget(self.delete_btn)
        
        self.layout.addLayout(header_layout)
        
        # --- CONTENT AREA ---
        self.content_container = QWidget()
        self.content_container.setStyleSheet("background: transparent; border: none;")
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(4, 0, 0, 0)
        self.content_layout.setSpacing(6)
        self.layout.addWidget(self.content_container)
    
    def update_progress(self, percent: int, status_text: str):
        # Обновляем локальные данные, чтобы при перерисовке они сохранились
        self.chunk_data['progress_percent'] = percent
        self.chunk_data['progress_text'] = status_text
        
        # Если мы все еще в статусе инициализации, обновляем UI напрямую
        if self.status == 'ИНИЦИАЛИЗАЦИЯ' or self.status == 'INITIALIZING':
            self.status_label.setText(f"{status_text} ({percent}%)")
            
            if hasattr(self, 'fill_widget'):
                pct = min(max(percent, 1), 100)
                bar_layout = self.fill_widget.parent().layout()
                if bar_layout:
                    bar_layout.setStretch(0, pct)
                    bar_layout.setStretch(1, 100 - pct)

    def _on_refresh(self):
        self.refresh_requested.emit(self.chunk_id)

    def _update_appearance(self):
        self.status = self.chunk_data.get('status')
        title = self.chunk_data.get('title') or f"Chunk #{self.chunk_id}"
        chunk_type = self.chunk_data.get('chunk_type', 'UNKNOWN')
        self.refresh_btn.setVisible(True)

        self.title_label.setText(title)

        self._clear_content()

        if self.status == 'В ОЖИДАНИИ' or self.status == 'PENDING':
            self._render_pending()
        elif self.status == 'ИНИЦИАЛИЗАЦИЯ' or self.status == 'INITIALIZING':
            self._render_initializing()
            self.refresh_btn.setVisible(False)
        elif self.status == 'ГОТОВ' or self.status == 'READY':
            self._render_ready(chunk_type)
        elif self.status == 'СЖАТ' or self.status == 'COMPRESSED':
            self._render_compressed()
        elif self.status == 'НАКОПЛЕНИЕ' or self.status == 'ACCUMULATING':
            self._render_accumulating()
        elif self.status == 'ОШИБКА' or self.status == 'FAILED':
            self._render_failed()
        else:
            self.status_label.setText(f"Статус: {self.status}")
            self.icon_label.setText("❓")

    def _render_pending(self):
        self.icon_label.setText("⏳")
        self.status_label.setText("Ожидает генерации отчета...")
        self.status_label.setStyleSheet(f"color: {Palette.WARNING};")
        self.delete_btn.setVisible(True)

    def _render_initializing(self):
        self.icon_label.setText("⚙️")
        
        # Берем текст прогресса, если он есть
        progress_text = self.chunk_data.get('progress_text', "Подготовка...")
        progress_val = self.chunk_data.get('progress_percent', 0)
        
        self.status_label.setText(f"{progress_text} ({progress_val}%)")
        self.delete_btn.setVisible(True)

        # Отрисовка прогресс-бара (оставляем старый код отрисовки, он корректен)
        p_bar = QFrame()
        p_bar.setFixedHeight(4)
        p_bar.setStyleSheet(f"background: {Palette.BG_DARK}; border-radius: 2px;")
        bar_container = QWidget()
        bar_layout = QHBoxLayout(bar_container)
        bar_layout.setContentsMargins(0,0,0,0)
        bar_layout.setSpacing(0)
        self.fill_widget = QWidget()
        self.fill_widget.setStyleSheet(f"background-color: {Palette.PRIMARY}; border-radius: 2px;")
        empty_widget = QWidget()
        empty_widget.setStyleSheet("background: transparent;")
        width_pct = min(max(progress_val, 1), 100)
        bar_layout.addWidget(self.fill_widget, stretch=width_pct)
        bar_layout.addWidget(empty_widget, stretch=100-width_pct)
        p_bar_wrapper = QFrame()
        p_bar_wrapper.setFixedHeight(6)
        p_bar_wrapper.setStyleSheet(f"background: {Palette.BG_DARK}; border-radius: 3px; border: none;")
        wrapper_layout = QVBoxLayout(p_bar_wrapper)
        wrapper_layout.setContentsMargins(0,0,0,0)
        wrapper_layout.addWidget(bar_container)
        self.content_layout.addWidget(p_bar_wrapper)

    def _render_ready(self, chunk_type):
        self.icon_label.setText("✓")
        self.icon_label.setStyleSheet(f"color: {Palette.SUCCESS}; font-size: 16px; border: none;")

        raw_date = self.chunk_data.get('last_updated', '')
        if len(raw_date) >= 16:
            last_upd = f"{raw_date[11:16]} • {raw_date[8:10]}.{raw_date[5:7]}"
        else:
            last_upd = raw_date

        self.status_label.setText(f"Активен • {last_upd}")
        self.status_label.setStyleSheet(f"color: {Palette.SUCCESS}; font-size: 11px;")
        self.delete_btn.setVisible(True)

        # Пытаемся достать контент
        content_obj = self.chunk_data.get('content')
        summary = self.chunk_data.get('summary')
        formation_reason = ""

        # Если контент строка - парсим
        if isinstance(content_obj, str):
            try:
                import json
                content_obj = json.loads(content_obj)
            except: pass
        
        if isinstance(content_obj, dict):
            formation_reason = content_obj.get('formation_reason', '')
            # Если summary не пришел отдельным полем, ищем внутри
            if not summary:
                summary = content_obj.get('summary')

        # 1. Отображаем причину формирования (если есть)
        if formation_reason:
            reason_lbl = QLabel(f"ℹ️ {formation_reason}")
            reason_lbl.setWordWrap(True)
            reason_lbl.setStyleSheet(f"color: {Palette.PRIMARY}; font-size: 11px; font-weight: bold; margin-bottom: 4px;")
            self.content_layout.addWidget(reason_lbl)

        # 2. Отображаем саммари
        if summary:
            lbl = QLabel(str(summary))
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {Palette.TEXT}; font-size: 12px; line-height: 1.3;")
            lbl.setMaximumHeight(120)
            self.content_layout.addWidget(lbl)
        else:
            lbl = QLabel("Нет краткого описания.")
            lbl.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-style: italic; font-size: 11px;")
            self.content_layout.addWidget(lbl)

    def _render_accumulating(self):
        self.icon_label.setText("📥")
        self.status_label.setText("Накопление данных...")
        self.status_label.setStyleSheet(f"color: {Palette.TERTIARY};")
        self.delete_btn.setVisible(True)
        
        # Пытаемся достать причину, почему данные копятся
        content_obj = self.chunk_data.get('content')
        formation_reason = ""
        if isinstance(content_obj, str):
            try:
                import json
                content_obj = json.loads(content_obj)
            except: pass
        if isinstance(content_obj, dict):
            formation_reason = content_obj.get('formation_reason', '')

        text = "ИИ ожидает больше данных для точного анализа."
        if formation_reason:
            text = f"{formation_reason}\n(Нужно больше данных)"

        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 11px; font-style: italic;")
        self.content_layout.addWidget(lbl)

    def _render_compressed(self):
        self.icon_label.setText("📦")
        
        raw_date = self.chunk_data.get('last_updated', '')
        if len(raw_date) >= 16:
            last_upd = f"{raw_date[11:16]} • {raw_date[8:10]}.{raw_date[5:7]}.{raw_date[:4]}"
        else:
            last_upd = raw_date
        
        orig_size = self.chunk_data.get('original_size', 0)
        comp_size = self.chunk_data.get('compressed_size', 0)
        
        saved = 0
        if orig_size > 0:
            saved = int((1 - comp_size/orig_size) * 100)
            
        self.status_label.setText(f"Сжат (экономия {saved}%) • {last_upd}")
        self.delete_btn.setVisible(True)
        
        lbl = QLabel("Архивная запись. Доступна для анализа, занимает минимум места.")
        lbl.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 11px; border: none;")
        self.content_layout.addWidget(lbl)

    def _render_failed(self):
        self.icon_label.setText("❌")
        self.status_label.setText("Ошибка генерации")
        self.status_label.setStyleSheet(f"color: {Palette.ERROR}; font-size: 11px;")
        self.delete_btn.setVisible(True)
        self.refresh_btn.setVisible(True)
        
        lbl = QLabel("Не удалось создать отчет. Проверьте логи или попробуйте снова.")
        lbl.setStyleSheet(f"color: {Palette.ERROR}; font-size: 11px; font-style: italic;")
        self.content_layout.addWidget(lbl)

    def _clear_content(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
    def update_data(self, new_data):
        self.chunk_data = new_data
        self._update_appearance()

    def _on_delete(self):
        self.deleted.emit(self.chunk_id)


class AIMemoryPanel(QWidget):
    scan_database_signal = pyqtSignal()
    generate_reports_signal = pyqtSignal()
    chunk_deleted = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.memory_manager = None
        self.chunk_manager = None
        self.cards = {}
        
        self.current_prompt_key = "analysis_behavior"

        self._init_ui()
        
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._refresh_active_chunks)
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.MD)
        
        header = QFrame()
        header.setStyleSheet(Components.panel())
        header_layout = QHBoxLayout(header)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignTop) 
        
        left_block = QVBoxLayout()
        left_block.setSpacing(4)
        left_block.setContentsMargins(0, 0, 0, 0)
        
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setAlignment(Qt.AlignmentFlag.AlignLeft) 
        
        t_lbl = QLabel("Память ИИ")
        t_lbl.setStyleSheet(Components.section_title())
        t_lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        top_row.addWidget(t_lbl)
        
        self.info_icon = QLabel("ⓘ")
        self.info_icon.setCursor(Qt.CursorShape.PointingHandCursor)
        self.info_icon.setStyleSheet(f"""
            QLabel {{
                color: {Palette.PRIMARY};
                font-size: 18px;
                font-weight: bold;
                margin-top: 2px;
            }}
            QLabel:hover {{
                color: {Palette.PRIMARY};
            }}
        """)
        
        tooltip_text = """
        <div style='width: 400px; font-family: sans-serif;'>
            <h3 style='color: #88C0D0;'>Как работает Память ИИ?</h3>
            <p>Эта система позволяет нейросети запоминать рыночные тренды, чтобы не анализировать каждый товар "с нуля".</p>
            <hr>
            <h4>1. Автоматическое обнаружение</h4>
            <p>Система сама сканирует вашу базу. Если вы спарсили много похожих товаров (например, >5 видеокарт), 
            она создает <b>Ячейку Памяти (Чанк)</b> со статусом ⏳ <i>В ожидании</i>.</p>
            
            <h4>2. Актуализация (Культивация)</h4>
            <p>Когда вы нажимаете <b>"Актуализировать память"</b>, ИИ анализирует всю группу товаров и пишет 
            аналитический отчет.</p>
            
            <h4>3. Использование при анализе</h4>
            <p>Когда вы анализируете новые объявления, ИИ сначала смотрит в Память. 
            Если он знает эту категорию, он сравнит цену товара с <b>рыночной статистикой (медианой и средней)</b>, 
            учитывая тренды и риски, сохраненные ранее.</p>
        </div>
        """
        self.info_icon.setToolTip(tooltip_text)
        self.info_icon.installEventFilter(self)
        
        top_row.addWidget(self.info_icon)
        left_block.addLayout(top_row)
        
        self.stats_lbl = QLabel("Загрузка...")
        self.stats_lbl.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 12px;")
        left_block.addWidget(self.stats_lbl)
        
        header_layout.addLayout(left_block)
        header_layout.addStretch()
        
        layout.addWidget(header)
        
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(Spacing.LG)

        left_col = QVBoxLayout()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(Components.scroll_area())
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setSpacing(10)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.addStretch()
        
        self.scroll.setWidget(self.cards_container)
        left_col.addWidget(self.scroll)
        
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(Spacing.MD)
        
        # Кнопка 1: Сканировать базу (бывшая Актуализировать)
        self.btn_scan = QPushButton("🔍 Сканировать базу")
        self.btn_scan.setToolTip("Быстрый поиск новых групп товаров в базе данных (без запуска ИИ)")
        self.btn_scan.setStyleSheet(Components.nav_button()) # Стиль поспокойнее
        self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan.clicked.connect(self._on_scan_clicked)
        
        # Кнопка 2: Сгенерировать отчеты (НОВАЯ)
        self.btn_generate = QPushButton("✨ Сгенерировать все отчеты")
        self.btn_generate.setToolTip("Запуск нейросети для обработки всех ожидающих чанков")
        self.btn_generate.setStyleSheet(Components.start_button())
        self.btn_generate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_generate.clicked.connect(self._on_generate_clicked)
        self.btn_generate.setEnabled(False) # По умолчанию выкл, включим если есть PENDING

        footer_layout.addWidget(self.btn_scan)
        footer_layout.addWidget(self.btn_generate)
        footer_layout.addStretch()
        
        left_col.addLayout(footer_layout)
        columns_layout.addLayout(left_col, stretch=3)
        
        right_col = QFrame()
        right_col.setFixedWidth(380)
        right_col.setStyleSheet(Components.panel())
        right_vbox = QVBoxLayout(right_col)
        right_vbox.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)

        self.right_tabs = QTabWidget()
        self.right_tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; }}
            QTabBar::tab {{
                background: {Palette.BG_DARK_3};
                color: {Palette.TEXT_MUTED};
                padding: 6px 10px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background: {Palette.BG_DARK_2};
                color: {Palette.PRIMARY};
                border-bottom: 2px solid {Palette.PRIMARY};
            }}
        """)

        tab_instr = QWidget()
        tab_instr_layout = QVBoxLayout(tab_instr)
        tab_instr_layout.setContentsMargins(0, 5, 0, 0)
        
        self.instr_scroll = QScrollArea()
        self.instr_scroll.setWidgetResizable(True)
        self.instr_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.instr_scroll.setStyleSheet("background: transparent;")
        
        self.instr_container = QWidget()
        self.instr_container.setStyleSheet("background: transparent;")
        self.instr_layout = QVBoxLayout(self.instr_container)
        self.instr_layout.setSpacing(10)
        self.instr_layout.setContentsMargins(0, 0, 5, 0)
        self.instr_layout.addStretch()
        
        self.instr_scroll.setWidget(self.instr_container)
        tab_instr_layout.addWidget(self.instr_scroll)
        
        self.new_instr_edit = QLineEdit()
        self.new_instr_edit.setPlaceholderText("Добавить инструкцию...")
        self.new_instr_edit.setStyleSheet(Components.text_input())
        self.new_instr_edit.returnPressed.connect(self.add_instruction_manual)
        tab_instr_layout.addWidget(self.new_instr_edit)
        
        self.right_tabs.addTab(tab_instr, "Инструкции")

        tab_interests = QWidget()
        tab_int_layout = QVBoxLayout(tab_interests)
        tab_int_layout.setContentsMargins(0, 5, 0, 0)
        
        int_header = QHBoxLayout()
        self.chk_edit_interests = QCheckBox("Редактировать")
        self.chk_edit_interests.setStyleSheet(Components.styled_checkbox())
        self.chk_edit_interests.stateChanged.connect(self._on_edit_interests_toggled)
        
        info_btn = QLabel("ⓘ")
        info_btn.setToolTip("Здесь вы описываете, ЧТО именно вы ищете.\nНейросеть будет использовать этот список как 'фильтр интересов'.\n\nМожно писать что угодно: 'Ищу старые монеты', 'Гитары Fender', 'Автомобили BMW'.")
        info_btn.setStyleSheet(f"color: {Palette.PRIMARY}; font-weight: bold;")
        
        int_header.addWidget(self.chk_edit_interests)
        int_header.addStretch()
        int_header.addWidget(info_btn)
        tab_int_layout.addLayout(int_header)
        
        self.interests_edit = QPlainTextEdit()
        self.interests_edit.setPlainText(DEFAULT_INTERESTS_TEXT)
        self.interests_edit.setReadOnly(True)
        self.interests_edit.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {Palette.BG_DARK_3};
                color: {Palette.TEXT_MUTED};
                border: 1px solid {Palette.BORDER_PRIMARY};
                border-radius: 4px;
                padding: 5px;
            }}
        """)
        tab_int_layout.addWidget(self.interests_edit)
        
        self.right_tabs.addTab(tab_interests, "Интересы")

        tab_prompts = QWidget()
        prompts_layout = QVBoxLayout(tab_prompts)
        prompts_layout.setContentsMargins(0, 5, 0, 0)
        prompts_layout.setSpacing(Spacing.SM)

        # Header: Combo + Help
        p_header = QHBoxLayout()
        self.prompt_combo = QComboBox()
        self.prompt_combo.addItems([
            "🧠 Анализ объявлений", 
            "🕷 Нейро-фильтр", 
            "💬 Личность Чата"
        ])
        self.prompt_combo.setStyleSheet(Components.styled_combobox())
        self.prompt_combo.currentIndexChanged.connect(self._on_prompt_changed)
        p_header.addWidget(self.prompt_combo, 1)

        p_info = QLabel("ⓘ")
        p_info.setToolTip(
            "Редактор системных ролей нейросети.\n\n"
            "Вы можете менять стиль, стратегию и критерии оценки.\n"
            "ВАЖНО: Не удаляйте {placeholders}, если они есть.\n"
            "Формат JSON менять здесь нельзя (он фиксирован)."
        )
        p_info.setStyleSheet(f"color: {Palette.PRIMARY}; font-weight: bold;")
        p_header.addWidget(p_info)
        prompts_layout.addLayout(p_header)

        # Help Label
        self.prompt_desc_lbl = QLabel("")
        self.prompt_desc_lbl.setWordWrap(True)
        self.prompt_desc_lbl.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 11px; margin-bottom: 4px;")
        prompts_layout.addWidget(self.prompt_desc_lbl)

        # Editor
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setStyleSheet(Components.text_input())
        prompts_layout.addWidget(self.prompt_edit)

        # Buttons
        p_btns = QHBoxLayout()
        self.btn_reset_prompt = QPushButton("Сброс")
        self.btn_reset_prompt.setStyleSheet(Components.small_button())
        self.btn_reset_prompt.clicked.connect(self._reset_current_prompt)
        
        self.btn_save_prompt = QPushButton("Сохранить")
        self.btn_save_prompt.setStyleSheet(Components.start_button())
        self.btn_save_prompt.clicked.connect(self._save_current_prompt)

        p_btns.addWidget(self.btn_reset_prompt)
        p_btns.addStretch()
        p_btns.addWidget(self.btn_save_prompt)
        prompts_layout.addLayout(p_btns)

        self.right_tabs.addTab(tab_prompts, "Промпты")

        right_vbox.addWidget(self.right_tabs)
        columns_layout.addWidget(right_col)
        
        layout.addLayout(columns_layout)
        
        self._load_interests_from_disk()
        self._load_current_prompt()

    def _get_prompt_key(self, idx):
        if idx == 0: return "analysis_behavior"
        if idx == 1: return "filter_behavior"
        return "chat_behavior"

    def _on_prompt_changed(self, idx):
        self.current_prompt_key = self._get_prompt_key(idx)
        self._load_current_prompt()

    def _load_current_prompt(self):
        text = prompt_manager.get(self.current_prompt_key)
        self.prompt_edit.setPlainText(text)
        
        desc_map = {
            "analysis_behavior": "Роль и стратегия при анализе таблицы (Full/Neuro режимы). {interests_block} будет заменен на ваши интересы.",
            "filter_behavior": "Логика отсева объявлений в режиме 'Нейро'. {search_tags} и {ignore_tags} подставляются автоматически.",
            "chat_behavior": "Системная инструкция для вкладки 'Чат'. Определяет личность ассистента."
        }
        self.prompt_desc_lbl.setText(desc_map.get(self.current_prompt_key, ""))

    def _save_current_prompt(self):
        new_text = self.prompt_edit.toPlainText()
        prompt_manager.set(self.current_prompt_key, new_text)
        
        # Visual feedback
        self.btn_save_prompt.setText("Сохранено!")
        self.btn_save_prompt.setEnabled(False)
        QTimer.singleShot(1500, lambda: self.btn_save_prompt.setText("Сохранить"))
        QTimer.singleShot(1500, lambda: self.btn_save_prompt.setEnabled(True))

    def _reset_current_prompt(self):
        # Ask confirmation
        confirm = QMessageBox.question(
            self, "Сброс", 
            "Сбросить ВСЕ промпты к заводским настройкам?\nЭто действие нельзя отменить.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            prompt_manager.reset_to_defaults()
            self._load_current_prompt()

    def add_instruction_manual(self):
        text = self.new_instr_edit.text().strip()
        if not text: return
        self.new_instr_edit.clear()

        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {Palette.BG_LIGHT};
                border: 1px solid {Palette.BORDER_PRIMARY};
                border-radius: 6px;
            }}
        """)
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(8, 8, 8, 8)
        card_layout.setSpacing(10)

        text_area = QTextEdit()
        text_area.setReadOnly(True)
        text_area.setPlainText(text)
        text_area.setFrameShape(QFrame.Shape.NoFrame)
        text_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        text_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        text_area.setStyleSheet(f"""
            background: transparent;
            color: {Palette.TEXT};
            font-family: {Typography.UI};
            font-size: 13px;
            border: none;
        """)
        
        text_area.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        text_area.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)

        doc = text_area.document()
        doc.setTextWidth(240)
        h = doc.size().height() + 20
        text_area.setFixedHeight(int(h))
        text_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        btn_delete = QPushButton("X")
        btn_delete.setFixedSize(20, 20)
        btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_delete.setStyleSheet(f"color: {Palette.TEXT_MUTED}; border: none; font-size: 16px; font-weight: bold;")
        btn_delete.clicked.connect(lambda _, c=card: self._remove_instr_card(c))

        card_layout.addWidget(text_area, 1)
        card_layout.addWidget(btn_delete, 0, Qt.AlignmentFlag.AlignTop)

        self.instr_layout.insertWidget(self.instr_layout.count() - 1, card)
        
        self.instr_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def _remove_instr_card(self, card):
        self.instr_layout.removeWidget(card)
        card.deleteLater()

    def get_instructions(self) -> list:
        instr = []
        for i in range(self.instr_layout.count() - 1):
            item = self.instr_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                text_edits = widget.findChildren(QTextEdit)
                for edit in text_edits:
                    text = edit.toPlainText().strip()
                    if text:
                        instr.append(text)
                        break
        return instr

    def save_instructions_to_disk(self):
        instrs = self.get_instructions()
        path = os.path.join(BASE_APP_DIR, "user_instructions.json")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(instrs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save instructions: {e}")

    def load_instructions_from_disk(self):
        path = os.path.join(BASE_APP_DIR, "user_instructions.json")
        if not os.path.exists(path): return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                instrs = json.load(f)
            for text in instrs:
                self.new_instr_edit.setText(text)
                self.add_instruction_manual()
        except Exception:
            pass
    
    def _on_edit_interests_toggled(self, state):
        is_editable = (state == Qt.CheckState.Checked.value) or (state == 2)
        self.interests_edit.setReadOnly(not is_editable)
        
        if is_editable:
            self.interests_edit.setStyleSheet(Components.text_input())
            self.interests_edit.setFocus()
        else:
            self.interests_edit.setStyleSheet(f"""
                QPlainTextEdit {{
                    background-color: {Palette.BG_DARK_3};
                    color: {Palette.TEXT_MUTED};
                    border: 1px solid {Palette.BORDER_PRIMARY};
                    border-radius: 4px;
                    padding: 5px;
                }}
            """)
            self._save_interests_to_disk()

    def get_interests_text(self) -> str:
        return self.interests_edit.toPlainText().strip()

    def _save_interests_to_disk(self):
        text = self.get_interests_text()
        path = os.path.join(BASE_APP_DIR, "user_interests.txt")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
        except Exception as e:
            logger.error(f"Failed to save interests: {e}")

    def _load_interests_from_disk(self):
        path = os.path.join(BASE_APP_DIR, "user_interests.txt")
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    text = f.read()
                if text.strip():
                    self.interests_edit.setPlainText(text)
            except: pass

    def eventFilter(self, obj, event):
        if obj == self.info_icon and event.type() == QEvent.Type.ToolTip:
            QToolTip.showText(event.globalPos(), obj.toolTip(), obj, obj.rect(), -1)
            return True
        return super().eventFilter(obj, event)

    def set_managers(self, memory_manager, chunk_manager):
        self.memory_manager = memory_manager
        self.chunk_manager = chunk_manager

        if self.chunk_manager:
            self.chunk_manager.chunk_status_changed.connect(self._on_chunk_status_changed)
            self.chunk_manager.cultivation_ready.connect(self._on_cultivation_ready)
            # NEW: Подключаем прогресс
            self.chunk_manager.chunk_progress.connect(self._on_chunk_progress)

        self._load_all_chunks()

    def _on_chunk_progress(self, chunk_id, percent, text):
        if chunk_id in self.cards:
            self.cards[chunk_id].update_progress(percent, text)

    def _load_all_chunks(self):
        if not self.memory_manager: return
        
        for cid, card in list(self.cards.items()):
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self.cards.clear()
        
        chunks = self.memory_manager.get_knowledge()
        
        def sort_key(c):
            s = c.get('status')
            if s == 'INITIALIZING': return 0
            if s == 'PENDING': return 1
            return 2
            
        chunks.sort(key=sort_key)
        
        item = self.cards_layout.takeAt(self.cards_layout.count() - 1)
        if item.widget(): item.widget().deleteLater()
        
        for chunk in chunks:
            self._add_card(chunk)
            
        self.cards_layout.addStretch()
        self._update_stats()

    def _on_scan_clicked(self):
        """Только сканирование БД"""
        self.btn_scan.setEnabled(False)
        self.btn_scan.setText("Сканирование...")
        self.scan_database_signal.emit()
        
        # Визуальный откат кнопки через таймер
        QTimer.singleShot(1000, lambda: self.btn_scan.setText("🔍 Сканировать базу"))
        QTimer.singleShot(1000, lambda: self.btn_scan.setEnabled(True))

    def _on_generate_clicked(self):
        """Запуск ИИ обработки"""
        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("Запуск нейросети...")
        self.generate_reports_signal.emit()
        
        # Кнопка разблокируется, когда придут статусы от менеджера, 
        # или можно разблокировать через таймер, если процесс долгий
        QTimer.singleShot(5000, lambda: self._update_generate_button_state())

    def _on_card_refresh_requested(self, chunk_id):
        """
        Обработчик нажатия кнопки рефреша на отдельной карточке.
        Переводит статус в PENDING и запускает общий процесс культивации через контроллер.
        Контроллер сам поднимет сервер, если он лежит.
        """
        if not self.memory_manager: 
            return

        # 1. Сбрасываем статус в базе
        self.memory_manager.update_chunk_status(chunk_id, 'PENDING')

        # 2. Мгновенно обновляем UI карточки, чтобы пользователь видел реакцию
        if chunk_id in self.cards:
            data = self.memory_manager.get_chunk_by_id(chunk_id)
            if data:
                self.cards[chunk_id].update_data(data)

        # 3. Обновляем общую статистику (кнопка "Сгенерировать" может стать активной/поменять текст)
        self._update_stats()

        # 4. Отправляем сигнал контроллеру на запуск обработки
        # Контроллер (Controller.start_cultivation) проверит сервер и запустит его при необходимости.
        logger.info(f"Запрошена перегенерация чанка {chunk_id}, инициализация нейросети...", token="ai-mem")
        self.generate_reports_signal.emit()

    def _add_card(self, chunk_data):
        card = ChunkCard(chunk_data, parent=self)
        
        # Подключаем сигналы от карточки
        card.deleted.connect(self._on_card_deleted)
        # FIX: Подключаем сигнал рефреша, который ранее был пропущен
        card.refresh_requested.connect(self._on_card_refresh_requested)
        
        self.cards[chunk_data['id']] = card
        self.cards_layout.insertWidget(self.cards_layout.count(), card)

    def _add_card_widget_only(self, data):
        self._add_card(data)
        return self.cards[data['id']]

    def _on_card_deleted(self, chunk_id):
        # 1. Сначала отменяем любые активные процессы с этим чанком
        if self.chunk_manager:
            self.chunk_manager.cancel_task(chunk_id)

        # 2. Удаляем из БД
        if self.memory_manager:
            self.memory_manager.delete_knowledge(chunk_id)

        # 3. Удаляем визуально
        if chunk_id in self.cards:
            card = self.cards.pop(chunk_id)
            card.deleteLater()

        self._update_stats()
        self.chunk_deleted.emit(chunk_id)
        
        # Лог для пользователя
        logger.info(f"Чанк {chunk_id} полностью удален (Force Forget).")

    def _on_chunk_status_changed(self, chunk_id, new_status):
        if chunk_id in self.cards:
            data = self.memory_manager.get_chunk_by_id(chunk_id)
            if data:
                self.cards[chunk_id].update_data(data)
        else:
            data = self.memory_manager.get_chunk_by_id(chunk_id)
            if data:
                # Вставляем перед растяжкой (stretch)
                count = self.cards_layout.count()
                insert_idx = count - 1 if count > 0 else 0
                self.cards_layout.insertWidget(insert_idx, self._add_card_widget_only(data))
        
        self._update_stats()

        if new_status == 'INITIALIZING':
            if not self.refresh_timer.isActive():
                self.refresh_timer.start(1000)

    def _on_cultivation_ready(self, chunk_id):
        if chunk_id in self.cards:
            data = self.memory_manager.get_chunk_by_id(chunk_id)
            if data:
                self.cards[chunk_id].update_data(data)
        self._update_stats()

    def _refresh_active_chunks(self):
        active = False
        for cid, card in self.cards.items():
            if card.status == 'INITIALIZING':
                active = True
                data = self.memory_manager.get_chunk_by_id(cid)
                if data:
                    card.update_data(data)
        
        if not active:
            self.refresh_timer.stop()
            
    def _update_stats(self):
        # Обновляем статистику и состояние кнопки генерации
        total = len(self.cards)
        ready = sum(1 for c in self.cards.values() if c.status in ['READY', 'COMPRESSED', 'ГОТОВ', 'СЖАТ'])
        pending = sum(1 for c in self.cards.values() if c.status in ['PENDING', 'В ОЖИДАНИИ'])
        
        self.stats_lbl.setText(f"Всего: {total} | Готово: {ready} | Ожидают: {pending}")
        
        # Включаем кнопку генерации только если есть что генерировать
        self._update_generate_button_state(pending)

    def _update_generate_button_state(self, pending_count=None):
        if pending_count is None:
            pending_count = sum(1 for c in self.cards.values() if c.status in ['PENDING', 'В ОЖИДАНИИ'])
            
        if pending_count > 0:
            self.btn_generate.setEnabled(True)
            self.btn_generate.setText(f"✨ Сгенерировать отчеты ({pending_count})")
            self.btn_generate.setStyleSheet(Components.start_button())
        else:
            self.btn_generate.setEnabled(False)
            self.btn_generate.setText("Нет новых данных")
            self.btn_generate.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Palette.BG_DARK_3};
                    border: 1px solid {Palette.BORDER_SOFT};
                    color: {Palette.TEXT_MUTED};
                    border-radius: {Spacing.RADIUS_NORMAL}px;
                    padding: 10px 18px;
                    font-weight: bold;
                }}
            """)