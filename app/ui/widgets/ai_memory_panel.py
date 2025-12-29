import json
import os
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QToolTip, QLineEdit,
    QTabWidget, QPlainTextEdit, QCheckBox,
    QComboBox, QMessageBox, QLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent, QPoint, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush

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


# --- 1. Custom Widgets for the Card ---

class ProgressThrobber(QWidget):
    """Круговой индикатор загрузки с процентами внутри"""
    def __init__(self, parent=None, size=40):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.percent = 0
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._rotate)
        self.timer.start(50)  # Animation speed

    def set_progress(self, p: int):
        self.percent = min(max(p, 0), 100)
        self.update()

    def _rotate(self):
        self.angle = (self.angle + 12) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        max_radius = 8
        spacing = 8
        x = max_radius # Центр первого круга по X
        y = self.height() // 2

        for key, color_hex, _, _ in self.mapping:
            val = self.weights.get(key, 0)
            base_color = QColor(color_hex)
            
            # 1. Рисуем контур (пустой круг)
            painter.setPen(QPen(QColor(Palette.TEXT_MUTED), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            # Используем QPoint(x, y) и int радиусы
            painter.drawEllipse(QPoint(x, y), max_radius, max_radius)
            
            # 2. Рисуем заполнение (растет из центра)
            if val > 0:
                # Радиус зависит от веса (0..100)
                fill_radius = max_radius * (val / 100.0)
                # Минимальный размер точки
                if fill_radius < 2: fill_radius = 2 
                
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(base_color))
                
                # --- FIX: Явное приведение радиуса к int во избежание TypeError ---
                r_int = int(fill_radius)
                painter.drawEllipse(QPoint(x, y), r_int, r_int)
                # ----------------------------------------------------------------

            x += (max_radius * 2) + spacing


class InfluenceCircles(QWidget):
    """
    Рисует 5 кружков влияния:
    1. Raw Data (White)
    2. System (Red)
    3. Instructions (Orange)
    4. Interests (Blue)
    5. Linked (Lime)
    """
    def __init__(self, weights: dict, parent=None):
        super().__init__(parent)
        self.setFixedSize(160, 26)
        self.weights = weights or {}
        
        self.mapping = [
            ("raw_data", "#E0E0E0", "Сырые данные", "Фактическая статистика лотов и цен в БД."),
            ("system_prompt", "#FF4D4F", "Роль", "Базовая роль нейросети заданная в главном промпте."),
            ("user_instructions", "#FA8C16", "Инструкции", "Ваши ручные указания для этого чанка."),
            ("user_interests", "#1890FF", "Интересы", "Совпадение с вашим списком интересов."),
            ("linked_chunks", "#A0D911", "Контекст", "Влияние родительских или связанных знаний.")
        ]
        self.setMouseTracking(True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Используем float для координат
        max_radius = 8.0
        spacing = 8.0
        x = 8.0 # Начальный отступ (радиус первого круга)
        y = self.height() / 2.0

        for key, color_hex, _, _ in self.mapping:
            val = self.weights.get(key, 0)
            base_color = QColor(color_hex)
            
            center = QPointF(x, y)

            # 1. Рисуем контур (пустой круг)
            painter.setPen(QPen(QColor(Palette.TEXT_MUTED), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(center, max_radius, max_radius)
            
            # 2. Рисуем заполнение (растет из центра)
            if val > 0:
                # Радиус зависит от веса (0..100)
                fill_radius = max_radius * (val / 100.0)
                # Минимальный размер точки
                if fill_radius < 2.0: fill_radius = 2.0
                
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(base_color))
                # Теперь все аргументы float, ошибок не будет
                painter.drawEllipse(center, fill_radius, fill_radius)

            x += (max_radius * 2) + spacing

    def event(self, event):
        if event.type() == QEvent.Type.ToolTip:
            parts = ["<b>ВЛИЯНИЕ НА ВЫВОДЫ ИИ:</b>"]
            for key, _, label, desc in self.mapping:
                val = self.weights.get(key, 0)
                color = "#4CAF50" if val > 50 else "#BDBDBD"
                parts.append(f"<br>• <b>{label}:</b> <span style='color:{color}'>{val}%</span><br>&nbsp;&nbsp;<i>{desc}</i>")
            
            QToolTip.showText(event.globalPos(), "".join(parts), self)
            return True
        return super().event(event)


class CollapsibleThought(QWidget):
    """Раскрывающийся блок 'Ход мыслей'"""
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.is_expanded = False
        
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.setMinimumWidth(0)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)
        
        # Header (Clickable)
        self.header = QFrame()
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.mousePressEvent = self.toggle
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(0, 0, 0, 0)
        
        self.arrow = QLabel("▶") # 🔽
        self.arrow.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-weight: bold;")
        
        lbl = QLabel("ХОД МЫСЛЕЙ")
        lbl.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-weight: bold; font-size: 10px;")
        
        hl.addWidget(self.arrow)
        hl.addWidget(lbl)
        hl.addStretch()
        
        # Content
        self.content = QLabel(text)
        self.content.setWordWrap(True)
        # --- FIX: Критично для переноса текста внутри вложенных лейаутов ---
        self.content.setMinimumWidth(10) 
        # ------------------------------------------------------------------
        self.content.setStyleSheet(f"color: {Palette.TEXT}; font-style: italic; font-size: 11px; margin-left: 15px;")
        self.content.setVisible(False)
        
        self.layout.addWidget(self.header)
        self.layout.addWidget(self.content)
        
    def toggle(self, event):
        self.is_expanded = not self.is_expanded
        self.arrow.setText("▼" if self.is_expanded else "▶")
        self.content.setVisible(self.is_expanded)


# --- 2. The New Chunk Card ---

class ChunkCard(QFrame):
    deleted = pyqtSignal(int)
    refresh_requested = pyqtSignal(int)

    def __init__(self, chunk_data: dict, parent=None):
        super().__init__(parent)
        self.chunk_data = chunk_data
        self.chunk_id = chunk_data.get('id')
        
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #121212;
                border: 1px solid {Palette.BORDER_PRIMARY};
                border-radius: 12px;
            }}
        """)
        
        # --- FIX: Policy Preferred + MinWidth 0 заставляют карточку уважать ширину колонки ---
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)
        # -------------------------------------------------------------------------------------
        
        self._init_ui()
        self.update_data(chunk_data)

    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(6)

        # 1. Header
        h_layout = QHBoxLayout()
        h_layout.setSpacing(8)
        
        self.icon_label = QLabel("📦")
        self.icon_label.setFixedSize(20, 20)
        self.icon_label.setStyleSheet("border: none; background: transparent;")
        
        self.title_label = QLabel()
        self.title_label.setWordWrap(True)
        # --- FIX: Обязательно ставим мин. ширину для враппинга ---
        self.title_label.setMinimumWidth(10)
        self.title_label.setStyleSheet(f"font-weight: bold; color: {Palette.TEXT}; font-size: 13px; border: none; background: transparent;")
        
        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setFixedSize(20, 20)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(lambda: self.refresh_requested.emit(self.chunk_id))
        self.refresh_btn.setStyleSheet(f"color: {Palette.PRIMARY}; border: none; background: transparent; font-weight: bold;")

        self.delete_btn = QPushButton("✕")
        self.delete_btn.setFixedSize(20, 20)
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.clicked.connect(lambda: self.deleted.emit(self.chunk_id))
        self.delete_btn.setStyleSheet(f"color: {Palette.TEXT_MUTED}; border: none; background: transparent;")

        h_layout.addWidget(self.icon_label)
        h_layout.addWidget(self.title_label, 1)
        h_layout.addWidget(self.refresh_btn)
        h_layout.addWidget(self.delete_btn)
        self.main_layout.addLayout(h_layout)

        self.meta_label = QLabel()
        self.meta_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 9px; font-family: {Typography.MONO}; margin-bottom: 4px;")
        self.main_layout.addWidget(self.meta_label)

        # 2. Loading State
        self.loader_container = QWidget()
        self.loader_layout = QVBoxLayout(self.loader_container)
        self.loader_layout.setContentsMargins(0,10,0,10)
        self.loader_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.throbber = ProgressThrobber(size=50)
        self.loader_msg = QLabel("Подготовка...")
        self.loader_msg.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        self.loader_layout.addWidget(self.throbber)
        self.loader_layout.addWidget(self.loader_msg)
        self.main_layout.addWidget(self.loader_container)
        
        # 3. Content State
        self.content_container = QWidget()
        self.content_container.setStyleSheet("border: none; background: transparent;")
        # --- FIX: Разрешаем контейнеру сжиматься ---
        self.content_container.setMinimumWidth(0)
        self.content_ui = QVBoxLayout(self.content_container)
        self.content_ui.setContentsMargins(0, 0, 0, 0)
        self.content_ui.setSpacing(6)
        
        # Green Status Box (Оставляем как яркий акцент, но дублируем статус в мету)
        self.status_box = QLabel()
        self.status_box.setWordWrap(True)
        self.status_box.setMinimumWidth(10)
        self.status_box.setStyleSheet(f"""
            background-color: {Palette.with_alpha(Palette.SUCCESS, 0.15)};
            color: {Palette.SUCCESS};
            border: 1px solid {Palette.SUCCESS};
            border-radius: 4px;
            padding: 6px;
            font-size: 11px;
            font-weight: bold;
        """)
        self.content_ui.addWidget(self.status_box)

        # Thought Process (Placeholder)
        self.thought_box = None 

        # Main Description
        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        # --- FIX ---
        self.desc_label.setMinimumWidth(10)
        self.desc_label.setStyleSheet(f"color: {Palette.TEXT}; font-size: 12px; margin-top: 4px;")
        self.content_ui.addWidget(self.desc_label)

        # Footer Layout
        footer = QHBoxLayout()
        footer.setSpacing(10)
        
        # --- UPDATED: Reason Label Styling ---
        self.reason_label = QLabel()
        self.reason_label.setWordWrap(True)
        self.reason_label.setMinimumWidth(10)
        self.reason_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 10px;")
        # -------------------------------------
        
        self.circles = None
        
        footer.addWidget(self.reason_label, 1)
        self.content_ui.addLayout(footer)
        
        self.main_layout.addWidget(self.content_container)

    def update_data(self, chunk_data: dict):
        self.chunk_data = chunk_data
        status_raw = chunk_data.get('status', 'UNKNOWN')
        chunk_type = chunk_data.get('chunk_type')
        title = chunk_data.get('title')
        
        self.title_label.setText(title)
        
        icons = { 'PRODUCT': '📦', 'CATEGORY': '📂', 'DATABASE': '🗄️', 'AI_BEHAVIOR': '🧠' }
        self.icon_label.setText(icons.get(chunk_type, '📄'))

        # --- NEW: Meta Info Logic ---
        # Форматирование дат
        def fmt_date(iso_str):
            if not iso_str: return "-"
            try:
                dt = datetime.fromisoformat(iso_str)
                return dt.strftime("%d.%m.%y %H:%M")
            except: return iso_str[:16].replace('T', ' ')

        created_at = fmt_date(chunk_data.get('created_at'))
        updated_at = fmt_date(chunk_data.get('last_updated'))
        if created_at == updated_at: updated_at = "-" # Если не обновлялся
        
        # Размер (примерный в КБ)
        content_obj = chunk_data.get('content')
        size_kb = len(json.dumps(content_obj)) / 1024 if content_obj else 0
        
        meta_text = f"{status_raw} | C: {created_at} | U: {updated_at} | {size_kb:.1f} KB"
        self.meta_label.setText(meta_text)
        # ----------------------------

        is_loading = status_raw in ['PENDING', 'INITIALIZING', 'ACCUMULATING']
        self.loader_container.setVisible(is_loading)
        self.content_container.setVisible(not is_loading)
        
        if is_loading:
            pct = chunk_data.get('progress_percent', 0)
            msg = chunk_data.get('progress_text', 'Ожидание...')
            self.throbber.set_progress(pct)
            self.loader_msg.setText(msg)
            # Скрываем лишнее при загрузке
            self.status_box.setVisible(False) 
            self.meta_label.setVisible(True)
            return
        
        self.status_box.setVisible(True)

        # Parse Content
        content = content_obj
        if isinstance(content, str):
            try: content = json.loads(content)
            except: content = {}
        if not content: content = {}
        
        display_status = content.get('display_status', 'НЕТ ДАННЫХ')
        self.status_box.setText(display_status.upper())
        
        # Thoughts
        thoughts = content.get('hidden_thought_process', '')
        if self.thought_box: 
            self.content_ui.removeWidget(self.thought_box)
            self.thought_box.deleteLater()
            self.thought_box = None
        
        if thoughts:
            self.thought_box = CollapsibleThought(thoughts)
            # Вставляем после status_box (индекс 1)
            self.content_ui.insertWidget(1, self.thought_box)

        # Description
        desc = content.get('main_description') or chunk_data.get('summary') or "Нет описания."
        self.desc_label.setText(desc)
        
        # --- NEW: Reason Styling ---
        reason_text = content.get('formation_reason') or ""
        if reason_text:
            self.reason_label.setText(f"<b>ПРИЧИНА:</b> {reason_text}")
        else:
            self.reason_label.setText("")
        # ---------------------------
        
        # Circles
        weights = content.get('influence_weights', {})
        if self.circles:
            layout_item = self.content_ui.itemAt(self.content_ui.count()-1)
            if layout_item and layout_item.layout():
                layout_item.layout().removeWidget(self.circles)
            self.circles.deleteLater()
            
        self.circles = InfluenceCircles(weights)
        self.content_ui.itemAt(self.content_ui.count()-1).layout().addWidget(self.circles)


# --- 3. Masonry Layout Widget ---

class MasonryWidget(QWidget):
    """
    Простой Masonry (Pinterest-like) лейаут.
    Использует 2 колонки (QVBoxLayout).
    Поддерживает словарь _cards для совместимости.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.layout.setSpacing(10)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        
        self.col1 = QVBoxLayout()
        self.col1.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.col1.setSpacing(10)
        
        self.col2 = QVBoxLayout()
        self.col2.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.col2.setSpacing(10)

        self.layout.addLayout(self.col1, 1)
        self.layout.addLayout(self.col2, 1)
        
        self._cards = {} # id -> card

    def add_card(self, chunk_id: int, card: QWidget):
        """Добавляет карточку и сразу кладет в нужную колонку"""
        self._cards[chunk_id] = card
        # Кладем на основе текущего количества (чтобы чередовать)
        self._place_card(card, len(self._cards) - 1)

    def remove_card(self, chunk_id: int):
        if chunk_id in self._cards:
            card = self._cards.pop(chunk_id)
            card.hide()
            card.deleteLater()
            QTimer.singleShot(10, self._rebalance)

    def clear(self):
        """Очистка всего"""
        for card in self._cards.values():
            card.deleteLater()
        self._cards.clear()

    def _place_card(self, card, index):
        """Кладет карточку в колонку."""
        if index % 2 == 0:
            self.col1.addWidget(card)
        else:
            self.col2.addWidget(card)

    def _rebalance(self):
        """Перекладывает все текущие виджеты заново"""
        for i, card in enumerate(self._cards.values()):
            self._place_card(card, i)

# --- 4. Main Panel (Integration) ---

class AIMemoryPanel(QWidget):
    scan_database_signal = pyqtSignal()
    generate_reports_signal = pyqtSignal()
    chunk_deleted = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.memory_manager = None
        self.chunk_manager = None
        
        self.current_prompt_key = "analysis_behavior"

        self._init_ui()
        
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._refresh_active_chunks)
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.MD)
        
        # --- HEADER ---
        header = QFrame()
        header.setStyleSheet(Components.panel())
        header_layout = QHBoxLayout(header)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignTop) 
        
        left_block = QVBoxLayout()
        left_block.setSpacing(4)
        left_block.setContentsMargins(0, 0, 0, 0)
        
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_row.setAlignment(Qt.AlignmentFlag.AlignLeft) 
        
        t_lbl = QLabel("ПАМЯТЬ НЕЙРОСЕТИ")
        t_lbl.setStyleSheet(Components.section_title())
        top_row.addWidget(t_lbl)
        
        self.info_icon = QLabel("ⓘ")
        self.info_icon.setCursor(Qt.CursorShape.PointingHandCursor)
        self.info_icon.setStyleSheet(f"color: {Palette.PRIMARY}; font-size: 18px; font-weight: bold;")
        self.info_icon.setToolTip("Память позволяет ИИ не анализировать товары 'с нуля', а опираться на накопленный опыт.")
        top_row.addWidget(self.info_icon)
        
        left_block.addLayout(top_row)
        
        self.stats_lbl = QLabel("Загрузка...")
        self.stats_lbl.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 12px;")
        left_block.addWidget(self.stats_lbl)
        
        header_layout.addLayout(left_block)
        header_layout.addStretch()
        layout.addWidget(header)
        
        # --- COLUMNS ---
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(Spacing.LG)

        # LEFT COLUMN (CARDS)
        left_col = QVBoxLayout()
        
        # Scroll Area for Masonry
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(Components.scroll_area())
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        # MASONRY CONTAINER
        self.masonry = MasonryWidget()
        self.scroll.setWidget(self.masonry)
        left_col.addWidget(self.scroll)
        
        # Footer Buttons
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(Spacing.MD)
        
        self.btn_scan = QPushButton("🔍 Найти кластеры")
        self.btn_scan.setToolTip("Поиск новых групп товаров в базе данных")
        self.btn_scan.setStyleSheet(Components.nav_button())
        self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan.clicked.connect(self._on_scan_clicked)
        
        self.btn_generate = QPushButton("✨ Актуализировать Память")
        self.btn_generate.setStyleSheet(Components.start_button())
        self.btn_generate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_generate.clicked.connect(self._on_generate_clicked)
        self.btn_generate.setEnabled(False) 

        footer_layout.addWidget(self.btn_scan)
        footer_layout.addWidget(self.btn_generate)
        footer_layout.addStretch()
        
        left_col.addLayout(footer_layout)
        columns_layout.addLayout(left_col, stretch=4)
        
        # RIGHT COLUMN (SETTINGS & PROMPTS)
        right_col = QFrame()
        right_col.setFixedWidth(380)
        right_col.setStyleSheet(Components.panel())
        right_vbox = QVBoxLayout(right_col)
        right_vbox.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)

        self.right_tabs = QTabWidget()
        # (Styles kept simple for brevity)
        self.right_tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; }}
            QTabBar::tab {{ background: {Palette.BG_DARK_3}; color: {Palette.TEXT_MUTED}; padding: 6px 10px; }}
            QTabBar::tab:selected {{ background: {Palette.BG_DARK_2}; color: {Palette.PRIMARY}; border-bottom: 2px solid {Palette.PRIMARY}; }}
        """)

        # Tab 1: Instructions
        self._init_instr_tab()
        # Tab 2: Interests
        self._init_interests_tab()
        # Tab 3: Prompts
        self._init_prompts_tab()

        right_vbox.addWidget(self.right_tabs)
        columns_layout.addWidget(right_col, stretch=0)
        
        layout.addLayout(columns_layout)
        
        # Load Data
        self._load_interests_from_disk()
        self._load_current_prompt()

    # --- Initialization Helpers ---

    def _init_instr_tab(self):
        tab = QWidget()
        l = QVBoxLayout(tab)
        l.setContentsMargins(0, 5, 0, 0)
        
        self.instr_scroll = QScrollArea()
        self.instr_scroll.setWidgetResizable(True)
        self.instr_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.instr_scroll.setStyleSheet("background: transparent;")
        
        self.instr_container = QWidget()
        self.instr_container.setStyleSheet("background: transparent;")
        self.instr_layout = QVBoxLayout(self.instr_container)
        self.instr_layout.setSpacing(10)
        self.instr_layout.addStretch()
        
        self.instr_scroll.setWidget(self.instr_container)
        l.addWidget(self.instr_scroll)
        
        self.new_instr_edit = QLineEdit()
        self.new_instr_edit.setPlaceholderText("Добавить инструкцию...")
        self.new_instr_edit.setStyleSheet(Components.text_input())
        self.new_instr_edit.returnPressed.connect(self.add_instruction_manual)
        l.addWidget(self.new_instr_edit)
        
        self.right_tabs.addTab(tab, "Инструкции")

    def _init_interests_tab(self):
        tab = QWidget()
        l = QVBoxLayout(tab)
        l.setContentsMargins(0, 5, 0, 0)
        
        header = QHBoxLayout()
        self.chk_edit_interests = QCheckBox("Редактировать")
        self.chk_edit_interests.setStyleSheet(Components.styled_checkbox())
        self.chk_edit_interests.stateChanged.connect(self._on_edit_interests_toggled)
        header.addWidget(self.chk_edit_interests)
        header.addStretch()
        l.addLayout(header)
        
        self.interests_edit = QPlainTextEdit()
        # Default text import is skipped to save space, assuming it's loaded from file
        self.interests_edit.setReadOnly(True)
        self.interests_edit.setStyleSheet(f"background-color: {Palette.BG_DARK_3}; color: {Palette.TEXT_MUTED}; border: 1px solid {Palette.BORDER_PRIMARY}; padding: 5px;")
        l.addWidget(self.interests_edit)
        
        self.right_tabs.addTab(tab, "Интересы")

    def _init_prompts_tab(self):
        tab = QWidget()
        l = QVBoxLayout(tab)
        l.setContentsMargins(0, 5, 0, 0)
        l.setSpacing(Spacing.SM)

        p_header = QHBoxLayout()
        self.prompt_combo = QComboBox()
        self.prompt_combo.addItems(["🧠 Анализ объявлений", "🕷 Нейро-фильтр", "💬 Личность Чата"])
        self.prompt_combo.setStyleSheet(Components.styled_combobox())
        self.prompt_combo.currentIndexChanged.connect(self._on_prompt_changed)
        p_header.addWidget(self.prompt_combo, 1)
        l.addLayout(p_header)

        self.prompt_desc_lbl = QLabel("")
        self.prompt_desc_lbl.setWordWrap(True)
        self.prompt_desc_lbl.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 11px;")
        l.addWidget(self.prompt_desc_lbl)

        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setStyleSheet(Components.text_input())
        l.addWidget(self.prompt_edit)

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
        l.addLayout(p_btns)

        self.right_tabs.addTab(tab, "Промпты")

    # --- Logic ---

    def set_managers(self, memory_manager, chunk_manager):
        self.memory_manager = memory_manager
        self.chunk_manager = chunk_manager

        if self.chunk_manager:
            self.chunk_manager.chunk_status_changed.connect(self._on_chunk_status_changed)
            self.chunk_manager.cultivation_ready.connect(self._on_cultivation_ready)
            self.chunk_manager.chunk_progress.connect(self._on_chunk_progress)

        self._load_all_chunks()

    def _load_all_chunks(self):
        if not self.memory_manager: return
        self.masonry.clear()
        
        chunks = self.memory_manager.get_knowledge()
        # Sort: Pending first, then by priority
        chunks.sort(key=lambda c: 0 if c.get('status') in ['PENDING', 'INITIALIZING'] else 1)
        
        for chunk in chunks:
            self._add_card(chunk)
            
        self._update_stats()

    def _add_card(self, chunk_data):
        card = ChunkCard(chunk_data, parent=self)
        card.deleted.connect(self._on_card_deleted)
        card.refresh_requested.connect(self._on_card_refresh_requested)
        self.masonry.add_card(chunk_data['id'], card)

    def _on_chunk_progress(self, chunk_id, percent, text):
        if chunk_id in self.masonry._cards:
            data = self.memory_manager.get_chunk_by_id(chunk_id) or {}
            data['progress_percent'] = percent
            data['progress_text'] = text
            self.masonry._cards[chunk_id].update_data(data)

    def _on_chunk_status_changed(self, chunk_id, new_status):
        if chunk_id in self.masonry._cards:
            data = self.memory_manager.get_chunk_by_id(chunk_id)
            if data:
                self.masonry._cards[chunk_id].update_data(data)
        elif new_status == 'PENDING': # New chunk created
            data = self.memory_manager.get_chunk_by_id(chunk_id)
            if data:
                self._add_card(data)
        
        self._update_stats()
        
        if new_status == 'INITIALIZING':
            if not self.refresh_timer.isActive():
                self.refresh_timer.start(1000)

    def _on_cultivation_ready(self, chunk_id):
        self._on_chunk_status_changed(chunk_id, 'READY')

    def _refresh_active_chunks(self):
        # Poll DB for chunks that might have stalled or updated silently
        active = False
        for cid, card in self.masonry._cards.items():
            if card.chunk_data.get('status') == 'INITIALIZING':
                active = True
                data = self.memory_manager.get_chunk_by_id(cid)
                if data: card.update_data(data)
        if not active: self.refresh_timer.stop()

    def _update_stats(self):
        count = len(self.masonry._cards)
        pending = sum(1 for c in self.masonry._cards.values() if c.chunk_data.get('status') in ['PENDING', 'В ОЖИДАНИИ'])
        self.stats_lbl.setText(f"Всего знаний: {count} | Ожидают: {pending}")
        
        if pending > 0:
            self.btn_generate.setEnabled(True)
            self.btn_generate.setText(f"✨ Актуализировать ({pending})")
        else:
            self.btn_generate.setEnabled(False)
            self.btn_generate.setText("Актуально")

    # --- Actions ---

    def _on_card_refresh_requested(self, chunk_id):
        if not self.memory_manager: return
        self.memory_manager.update_chunk_status(chunk_id, 'PENDING')
        self._on_chunk_status_changed(chunk_id, 'PENDING')
        self.generate_reports_signal.emit()

    def _on_card_deleted(self, chunk_id):
        if self.chunk_manager: self.chunk_manager.cancel_task(chunk_id)
        if self.memory_manager: self.memory_manager.delete_knowledge(chunk_id)
        self.masonry.remove_card(chunk_id)
        self._update_stats()
        self.chunk_deleted.emit(chunk_id)

    def _on_scan_clicked(self):
        self.btn_scan.setEnabled(False)
        self.btn_scan.setText("Ищем...")
        self.scan_database_signal.emit()
        QTimer.singleShot(1000, lambda: self.btn_scan.setText("🔍 Найти кластеры"))
        QTimer.singleShot(1000, lambda: self.btn_scan.setEnabled(True))

    def _on_generate_clicked(self):
        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("Запуск...")
        self.generate_reports_signal.emit()

    # --- Prompts & Settings Logic (Same as before) ---

    def _get_prompt_key(self, idx):
        return ["analysis_behavior", "filter_behavior", "chat_behavior"][idx]

    def _on_prompt_changed(self, idx):
        self.current_prompt_key = self._get_prompt_key(idx)
        self._load_current_prompt()

    def _load_current_prompt(self):
        text = prompt_manager.get(self.current_prompt_key)
        self.prompt_edit.setPlainText(text)
        desc_map = {
            "analysis_behavior": "Роль и стратегия при анализе таблицы. {interests_block} будет заменен на ваши интересы.",
            "filter_behavior": "Логика нейро-фильтра.",
            "chat_behavior": "Системная инструкция для чата."
        }
        self.prompt_desc_lbl.setText(desc_map.get(self.current_prompt_key, ""))

    def _save_current_prompt(self):
        prompt_manager.set(self.current_prompt_key, self.prompt_edit.toPlainText())
        self.btn_save_prompt.setText("OK!")
        QTimer.singleShot(1000, lambda: self.btn_save_prompt.setText("Сохранить"))

    def _reset_current_prompt(self):
        if QMessageBox.question(self, "Сброс", "Сбросить к заводским?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            prompt_manager.reset_to_defaults()
            self._load_current_prompt()

    def add_instruction_manual(self):
        text = self.new_instr_edit.text().strip()
        if not text: return
        self.new_instr_edit.clear()
        
        # Simple Card for instruction
        card = QFrame()
        card.setStyleSheet(f"background: {Palette.BG_LIGHT}; border-radius: 4px;")
        l = QHBoxLayout(card)
        l.setContentsMargins(5,5,5,5)
        
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {Palette.TEXT};")
        
        btn = QPushButton("✕")
        btn.setFixedSize(20,20)
        btn.setStyleSheet("border: none; color: #666;")
        btn.clicked.connect(lambda: (self.instr_layout.removeWidget(card), card.deleteLater()))
        
        l.addWidget(lbl, 1)
        l.addWidget(btn)
        self.instr_layout.insertWidget(self.instr_layout.count()-1, card)
        
        # Save placeholder
        self.save_instructions_to_disk()

    def get_instructions(self) -> list:
        # Extract text from labels
        instr = []
        for i in range(self.instr_layout.count()-1):
            w = self.instr_layout.itemAt(i).widget()
            if w:
                lbl = w.findChild(QLabel)
                if lbl: instr.append(lbl.text())
        return instr

    def save_instructions_to_disk(self):
        path = os.path.join(BASE_APP_DIR, "user_instructions.json")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.get_instructions(), f, ensure_ascii=False)
        except: pass

    def load_instructions_from_disk(self): # Called by main window
        path = os.path.join(BASE_APP_DIR, "user_instructions.json")
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for t in json.load(f):
                        self.new_instr_edit.setText(t)
                        self.add_instruction_manual()
            except: pass

    def _on_edit_interests_toggled(self, state):
        is_ed = (state == 2)
        self.interests_edit.setReadOnly(not is_ed)
        self.interests_edit.setStyleSheet(f"background-color: {Palette.BG_LIGHT if is_ed else Palette.BG_DARK_3}; color: {Palette.TEXT}; border: 1px solid {Palette.BORDER_PRIMARY}; padding: 5px;")
        if not is_ed: self._save_interests_to_disk()

    def get_interests_text(self): return self.interests_edit.toPlainText().strip()
    
    def _save_interests_to_disk(self):
        try:
            with open(os.path.join(BASE_APP_DIR, "user_interests.txt"), 'w', encoding='utf-8') as f:
                f.write(self.get_interests_text())
        except: pass

    def _load_interests_from_disk(self):
        try:
            path = os.path.join(BASE_APP_DIR, "user_interests.txt")
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    self.interests_edit.setPlainText(f.read())
            else:
                # Если файла нет, загружаем дефолтную константу
                self.interests_edit.setPlainText(DEFAULT_INTERESTS_TEXT.strip())
        except: pass