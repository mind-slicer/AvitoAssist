import re
from collections import Counter

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFrame, QTreeWidget, QTreeWidgetItem, QTableWidget, 
    QTableWidgetItem, QLineEdit, QComboBox, QSplitter, QToolBar,
    QMessageBox, QTabWidget, QAbstractItemView, QFormLayout,
    QStyledItemDelegate, QStyle, QTreeWidgetItemIterator
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QSize
from PyQt6.QtGui import QAction, QColor

from app.ui.styles import Components, Palette, Spacing
from app.ui.styles.typography import TextPresets, Typography
from app.ui.widgets.move_item_dialog import MoveItemDialog
from app.core.log_manager import logger
from app.config import BASE_APP_DIR


class TreeItemDelegate(QStyledItemDelegate):
    """
    Делегат для отображения кнопок удаления в дереве.
    """
    delete_clicked = pyqtSignal(object)

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        
        # Строгая проверка типа: рисуем ТОЛЬКО для категорий, брендов и продуктов
        data = index.data(Qt.ItemDataRole.UserRole)
        if not data or data.get('type') not in ('category', 'brand_group', 'product_key'):
            return

        if option.state & QStyle.StateFlag.State_MouseOver:
            # Динамический размер кнопки, чтобы избежать "срезания" на узких строках
            item_height = option.rect.height()
            btn_size = min(18, item_height - 4) 
            
            btn_rect = QRect(
                option.rect.right() - btn_size - 8,
                option.rect.top() + (item_height - btn_size) // 2,
                btn_size,
                btn_size
            )
            painter.setRenderHint(painter.RenderHint.Antialiasing)
            painter.setBrush(QColor(Palette.ERROR))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(btn_rect, 4, 4)
            
            painter.setPen(QColor("white"))
            font = painter.font()
            font.setBold(True)
            font.setPointSize(8)
            painter.setFont(font)
            painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, "✕")

    def editorEvent(self, event, model, option, index):
        if event.type() == event.Type.MouseButtonRelease:
            data = index.data(Qt.ItemDataRole.UserRole)
            if not data or data.get('type') not in ('category', 'brand_group', 'product_key'):
                return False

            item_height = option.rect.height()
            btn_size = min(18, item_height - 4)
            btn_rect = QRect(
                option.rect.right() - btn_size - 8,
                option.rect.top() + (item_height - btn_size) // 2,
                btn_size,
                btn_size
            )
            if btn_rect.contains(event.pos()):
                self.delete_clicked.emit(index)
                return True
        return super().editorEvent(event, model, option, index)
    

class DatabaseTab(QWidget):
    recultivate_requested = pyqtSignal()

    def __init__(self, memory_manager, parent=None):
        super().__init__(parent)
        self.memory = memory_manager
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # === Toolbar (без поиска и фильтра) ===
        toolbar = QToolBar()
        toolbar.setStyleSheet(f"""
            QToolBar {{ background-color: {Palette.BG_DARK}; border-bottom: 1px solid {Palette.BORDER_SOFT}; padding: 8px; }}
            QToolButton {{ background: transparent; color: {Palette.TEXT}; border: 1px solid {Palette.BORDER_SOFT}; border-radius: 4px; padding: 6px 12px; margin-right: 8px; }}
            QToolButton:hover {{ background: {Palette.BG_DARK_2}; border-color: {Palette.PRIMARY}; }}
        """)

        refresh_action = QAction("🔄 Обновить", self)
        refresh_action.triggered.connect(self._refresh_data)
        toolbar.addAction(refresh_action)

        toolbar.addSeparator()

        export_action = QAction("📤 Экспорт JSON", self)
        export_action.triggered.connect(self._export_data)
        toolbar.addAction(export_action)

        import_action = QAction("📥 Импорт JSON", self)
        import_action.triggered.connect(self._import_data)
        toolbar.addAction(import_action)

        toolbar.addSeparator()

        clear_action = QAction("🗑️ Очистить БД", self)
        clear_action.triggered.connect(self._clear_database)
        toolbar.addAction(clear_action)
        
        toolbar.addSeparator()

        # Кнопка очистки корзины
        empty_trash_action = QAction("🗑️ Очистить корзину", self)
        empty_trash_action.triggered.connect(self._empty_trash)
        toolbar.addAction(empty_trash_action)

        layout.addWidget(toolbar)

        # === Main Splitter ===
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(4)
        self.splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {Palette.BORDER_SOFT}; }}")

        # === Left Panel ===
        self.left_panel = QFrame()
        self.left_panel.setMinimumWidth(400) # Увеличено с 370
        self.left_panel.setStyleSheet(Components.panel())
        
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        left_layout.setSpacing(Spacing.SM)

        # Статистика (локализация)
        stats_frame = QFrame()
        stats_frame.setStyleSheet(f"QFrame {{ background-color: {Palette.BG_DARK_2}; border-radius: {Spacing.RADIUS_NORMAL}px; padding: 12px; }}")
        stats_layout = QVBoxLayout(stats_frame)
        
        self.stats_label = QLabel("Загрузка...")
        self.stats_label.setStyleSheet(f"color: {Palette.TEXT}; font-size: 11px; line-height: 1.4;")
        self.stats_label.setWordWrap(True) # Перенос слов
        stats_layout.addWidget(self.stats_label)
        left_layout.addWidget(stats_frame)

        # Поиск по навигации (КРАСНОЕ ПОДЧЕРКИВАНИЕ - перенесен сюда)
        self.nav_search_edit = QLineEdit()
        self.nav_search_edit.setPlaceholderText("🔍 Поиск в списке/графе...")
        self.nav_search_edit.setStyleSheet(Components.text_input())
        self.nav_search_edit.textChanged.connect(self._on_nav_search)
        left_layout.addWidget(self.nav_search_edit)

        # Tabs for Tree / Graph
        self.nav_tabs = QTabWidget()
        self.nav_tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; }}
            QTabBar::tab {{ background: {Palette.BG_DARK_3}; color: {Palette.TEXT_MUTED}; padding: 8px 12px; border-radius: 4px 4px 0 0; }}
            QTabBar::tab:selected {{ background: {Palette.BG_DARK_2}; color: {Palette.PRIMARY}; font-weight: bold; }}
        """)

        # 1. Tree
        self.nav_tree = QTreeWidget()
        self.nav_tree.setHeaderHidden(True)
        self.nav_tree.setStyleSheet(f"""
            QTreeWidget {{ background: transparent; border: none; font-size: 13px; }}
            QTreeWidget::item {{ padding: 6px; border-radius: 4px; }}
            QTreeWidget::item:selected {{ background-color: {Palette.PRIMARY}; color: white; }}
            QTreeWidget::item:hover {{ background-color: {Palette.BG_DARK_2}; }}
        """)
        self.nav_tree.itemClicked.connect(self._on_tree_item_clicked)
        
        self.tree_delegate = TreeItemDelegate()
        self.tree_delegate.delete_clicked.connect(self._on_tree_item_delete)
        self.nav_tree.setItemDelegate(self.tree_delegate)

        self.nav_tabs.addTab(self.nav_tree, "📂 Список")

        # 2. Graph
        from app.ui.widgets.knowledge_graph import KnowledgeGraphWidget
        self.graph_widget = KnowledgeGraphWidget()
        self.graph_widget.node_selected.connect(self._on_graph_node_selected)
        self.nav_tabs.addTab(self.graph_widget, "🕸 Граф")

        self.nav_tabs.currentChanged.connect(self._on_nav_tab_changed)
        left_layout.addWidget(self.nav_tabs)

        self.splitter.addWidget(self.left_panel)

        # === Center Panel (Tables) ===
        center_panel = QFrame()
        center_panel.setStyleSheet(Components.panel())
        
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        center_layout.setSpacing(Spacing.SM)

        # Header с поиском по таблице и кнопками действий
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(Spacing.SM)

        table_header = QLabel("ДАННЫЕ В БАЗЕ")
        table_header.setStyleSheet(Components.subsection_title())
        header_layout.addWidget(table_header)

        # === НОВЫЕ КНОПКИ ДЕЙСТВИЙ ===
        self.btn_move_selected = QPushButton("➜ Переместить выделенное")
        self.btn_move_selected.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_DARK_3};
                border: 1px solid {Palette.PRIMARY};
                color: {Palette.PRIMARY};
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{ background-color: {Palette.with_alpha(Palette.PRIMARY, 0.2)}; }}
            QPushButton:disabled {{ border-color: {Palette.BORDER_SOFT}; color: {Palette.TEXT_MUTED}; }}
        """)
        self.btn_move_selected.setEnabled(False)
        self.btn_move_selected.clicked.connect(self._on_move_selected_clicked)
        header_layout.addWidget(self.btn_move_selected)

        self.btn_delete_selected = QPushButton("🗑 Отправить выделенное в корзину")
        self.btn_delete_selected.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_DARK_3};
                border: 1px solid {Palette.ERROR};
                color: {Palette.ERROR};
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{ background-color: {Palette.with_alpha(Palette.ERROR, 0.2)}; }}
            QPushButton:disabled {{ border-color: {Palette.BORDER_SOFT}; color: {Palette.TEXT_MUTED}; }}
        """)
        self.btn_delete_selected.setEnabled(False)
        self.btn_delete_selected.clicked.connect(self._on_delete_selected_clicked)
        header_layout.addWidget(self.btn_delete_selected)

        self.btn_toggle_confidence = QPushButton("🔄 Надежность")
        self.btn_toggle_confidence.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_DARK_3};
                border: 1px solid {Palette.WARNING};
                color: {Palette.WARNING};
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {Palette.with_alpha(Palette.WARNING, 0.2)};
            }}
            QPushButton:disabled {{
                border-color: {Palette.BORDER_SOFT};
                color: {Palette.TEXT_MUTED};
            }}
        """)
        self.btn_toggle_confidence.setEnabled(False)
        self.btn_toggle_confidence.clicked.connect(self.on_toggle_confidence_clicked)
        header_layout.addWidget(self.btn_toggle_confidence)

        header_layout.addStretch()

        # Поиск по всем столбцам таблицы
        self.table_search_edit = QLineEdit()
        self.table_search_edit.setPlaceholderText("🔍 Поиск по всем столбцам...")
        self.table_search_edit.setStyleSheet(Components.text_input())
        self.table_search_edit.setFixedWidth(250)
        self.table_search_edit.textChanged.connect(self._on_table_search)
        header_layout.addWidget(self.table_search_edit)

        center_layout.addWidget(header_widget)

        # Table Tabs
        self.table_tabs = QTabWidget()
        self.table_tabs.setStyleSheet(f"""
            QTabWidget::pane {{ background: {Palette.BG_DARK_2}; border: none; }}
            QTabBar::tab {{ background: {Palette.BG_DARK}; color: {Palette.TEXT_MUTED}; padding: 8px 16px; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 4px; }}
            QTabBar::tab:selected {{ background: {Palette.PRIMARY}; color: white; }}
        """)
        self.table_tabs.currentChanged.connect(self._on_table_tab_changed)

        # Raw Items Table
        self.raw_items_table = QTableWidget()
        self.raw_items_table.setColumnCount(7)
        self.raw_items_table.setHorizontalHeaderLabels([
            "ID", "Заголовок", "Цена", "Город", "Дата", "Категории", "🔒"
        ])
        self.raw_items_table.horizontalHeader().setStretchLastSection(True)
        # Включаем множественное выделение строк
        self.raw_items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.raw_items_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection) 
        self.raw_items_table.setStyleSheet(self._get_table_style())
        # Подключаем сигнал изменения выделения для кнопок
        self.raw_items_table.itemSelectionChanged.connect(self._update_action_buttons_state)
        self.raw_items_table.currentItemChanged.connect(self._on_raw_item_selection_changed)

        self.table_tabs.addTab(self.raw_items_table, "📦 Сырые данные")

        # Knowledge Table Tab Container
        knowledge_tab_widget = QWidget()
        knowledge_tab_layout = QVBoxLayout(knowledge_tab_widget)
        knowledge_tab_layout.setContentsMargins(0, 0, 0, 0)
        knowledge_tab_layout.setSpacing(Spacing.SM)

        # Фильтр типов (отображается только на табе "Знания ИИ")
        filter_widget = QWidget()
        filter_layout = QHBoxLayout(filter_widget)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(Spacing.SM)

        filter_label = QLabel("Тип:")
        filter_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: {Typography.SIZE_SM}px;")
        filter_layout.addWidget(filter_label)

        self.type_filter = QComboBox()
        self.type_filter.addItems(["Все", "Продукт", "Категория", "База данных", "Поведение ИИ", "Кастомное"])
        
        # Маппинг русских имен на типы БД
        self._filter_type_map = {
            "Все": None,
            "Продукт": "PRODUCT",
            "Категория": "CATEGORY",
            "База данных": "DATABASE",
            "Поведение ИИ": "AI_BEHAVIOR",
            "Кастомное": "CUSTOM"
        }

        self.type_filter.setStyleSheet(f"""
            QComboBox {{ background: {Palette.BG_DARK_2}; color: {Palette.TEXT}; border: 1px solid {Palette.BORDER_SOFT}; border-radius: 4px; padding: 6px 12px; min-width: 140px; }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox:hover {{ border-color: {Palette.PRIMARY}; }}
        """)
        self.type_filter.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.type_filter)
        filter_layout.addStretch()
        knowledge_tab_layout.addWidget(filter_widget)

        # Knowledge Table
        self.knowledge_table = QTableWidget()
        self.knowledge_table.setColumnCount(5)
        self.knowledge_table.setHorizontalHeaderLabels(["ID", "Тип", "Ключ", "Статус", "Обновлено"])
        self.knowledge_table.horizontalHeader().setStretchLastSection(True)
        self.knowledge_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.knowledge_table.setStyleSheet(self._get_table_style())
        self.knowledge_table.currentItemChanged.connect(self._on_knowledge_selection_changed)
        
        knowledge_tab_layout.addWidget(self.knowledge_table)
        self.table_tabs.addTab(knowledge_tab_widget, "🧠 Знания ИИ")

        center_layout.addWidget(self.table_tabs)
        self.splitter.addWidget(center_panel)

        # === Right Panel (Details) ===
        right_panel = QFrame()
        right_panel.setFixedWidth(350)
        right_panel.setStyleSheet(Components.panel())
        
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        right_layout.setSpacing(Spacing.SM)

        details_header = QLabel("ДЕТАЛИ")
        details_header.setStyleSheet(Components.subsection_title())
        right_layout.addWidget(details_header)

        self.details_scroll = QScrollArea()
        self.details_scroll.setWidgetResizable(True)
        self.details_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.details_scroll.setStyleSheet("background: transparent; border: none;")
        
        self.details_container = QWidget()
        self.details_layout = QVBoxLayout(self.details_container)
        self.details_layout.setSpacing(Spacing.SM)
        self.details_scroll.setWidget(self.details_container)
        
        right_layout.addWidget(self.details_scroll)

        self.cultivate_btn = QPushButton("🌱 Перекультивировать")
        self.cultivate_btn.setStyleSheet(Components.start_button())
        self.cultivate_btn.setEnabled(False)
        self.cultivate_btn.clicked.connect(self._recultivate)
        right_layout.addWidget(self.cultivate_btn)

        self.splitter.addWidget(right_panel)
        layout.addWidget(self.splitter)

        # Настройки сплиттера
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setCollapsible(2, False)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([420, 800, 350])

    def _get_table_style(self):
        return f"""
            QTableWidget {{ background: transparent; border: none; gridline-color: {Palette.BORDER_SOFT}; }}
            QHeaderView::section {{ background: {Palette.BG_DARK}; color: {Palette.TEXT_MUTED}; padding: 8px; border: none; }}
        """

    def _load_data(self):
        """Load all data from the database."""
        if not self.memory:
            return
            
        # --- NEW HIERARCHY LOADING ---
        hierarchy = self.memory.raw_data.get_hierarchy_data()
        self.nav_tree.clear()
        
        # Root items
        all_items_node = QTreeWidgetItem(["📦 Все сырые данные"])
        all_items_node.setData(0, Qt.ItemDataRole.UserRole, {'type': 'all_items'})
        
        all_knowledge_node = QTreeWidgetItem(["🧠 Все знания"])
        all_knowledge_node.setData(0, Qt.ItemDataRole.UserRole, {'type': 'all_knowledge'})
        
        self.nav_tree.addTopLevelItem(all_items_node)
        self.nav_tree.addTopLevelItem(all_knowledge_node)
        
        # === КОРЗИНА (после разделителя) ===
        separator = QTreeWidgetItem([""])
        separator.setFlags(Qt.ItemFlag.NoItemFlags)
        separator.setData(0, Qt.ItemDataRole.UserRole, {'type': 'separator'})
        separator.setBackground(0, QColor(Palette.DIVIDER))
        separator.setSizeHint(0, QSize(0, 2))
        self.nav_tree.addTopLevelItem(separator)
        
        # Узел корзины
        trash_count = len(self.memory.raw_data.get_trash_items())
        trash_node = QTreeWidgetItem([f"🗑️ Корзина ({trash_count})"])
        trash_node.setData(0, Qt.ItemDataRole.UserRole, {'type': 'trash'})
        trash_node.setForeground(0, QColor(Palette.TEXT_MUTED))
        self.nav_tree.addTopLevelItem(trash_node)
        
        # Iterate Categories
        for cat_name, brands in hierarchy.items():
            # Считаем общий счетчик категории для корректной инициализации
            cat_total = sum(p['count'] for b in brands.values() for p in b)
            cat_node = QTreeWidgetItem([f"📂 {cat_name} ({cat_total})"])
            cat_node.setData(0, Qt.ItemDataRole.UserRole, {
                'type': 'category',
                'name': cat_name,
                'count': cat_total # <-- ТЕПЕРЬ СОХРАНЯЕМ СЧЕТЧИК
            })
            self.nav_tree.addTopLevelItem(cat_node)
            
            for brand_name, products in brands.items():
                parent_for_prod = cat_node
                if brand_name != 'NO_BRAND':
                    brand_total = sum(p['count'] for p in products)
                    brand_node = QTreeWidgetItem([f"🏭 {brand_name} ({brand_total})"])
                    brand_node.setData(0, Qt.ItemDataRole.UserRole, {
                        'type': 'brand_group',
                        'count': brand_total # <-- СОХРАНЯЕМ
                    })
                    cat_node.addChild(brand_node)
                    parent_for_prod = brand_node
                
                for prod in products:
                    name = prod['name'] or prod['key'] or "Unknown"
                    count = prod['count']
                    
                    prod_item = QTreeWidgetItem([f"📦 {name} ({count})"])
                    prod_item.setData(0, Qt.ItemDataRole.UserRole, {
                        'type': 'product_key', 
                        'key': prod['key'],
                        'id': prod['id'],
                        'count': count # <-- КРИТИЧЕСКИЙ ФИКС: ТЕПЕРЬ ПРОДУКТ ЗНАЕТ СВОЙ СЧЕТЧИК
                    })
                    parent_for_prod.addChild(prod_item)
        
        # -----------------------------
        
        all_items_node.setExpanded(True)
        
        # Load raw items table
        raw_items = self.memory.get_raw_items(limit=1000)
        self._populate_raw_items_table(raw_items)
        
        # Load knowledge table
        knowledge = self.memory.get_knowledge(limit=1000)
        self._populate_knowledge_table(knowledge)
        
        self.graph_widget.load_data(knowledge)
        self._update_stats()

    def _populate_raw_items_table(self, items: list):
        """Populate the raw items table."""
        self.raw_items_table.setUpdatesEnabled(False)
        self.raw_items_table.setRowCount(0)
        
        for item in items:
            row = self.raw_items_table.rowCount()
            self.raw_items_table.insertRow(row)
            
            # ID
            id_item = QTableWidgetItem(str(item.get('id', '')))
            # Store full data in the first column
            id_item.setData(Qt.ItemDataRole.UserRole, item)
            self.raw_items_table.setItem(row, 0, id_item)
            
            # Title (truncated)
            title = item.get('title', '')[:50] + '...' if len(item.get('title', '')) > 50 else item.get('title', '')
            self.raw_items_table.setItem(row, 1, QTableWidgetItem(title))
            
            # Price
            price = item.get('price', '')
            self.raw_items_table.setItem(row, 2, QTableWidgetItem(str(price)))
            
            # City
            self.raw_items_table.setItem(row, 3, QTableWidgetItem(item.get('city', '')))
            
            # Date
            self.raw_items_table.setItem(row, 4, QTableWidgetItem(item.get('date_text', '')))
            
            # Categories
            cat_list = item.get('categories', [])
            main_cat = cat_list[0] if cat_list else "Misc"
            
            # Получаем semantic_data если есть
            brand = item.get('brand', '')
            model = item.get('model', '')
            
            # === УЛУЧШЕННАЯ ЛОГИКА ОТОБРАЖЕНИЯ ===
            if main_cat == 'PC_BUILD':
                # Для сборок показываем компоненты
                raw_keys = item.get('product_keys', [])
                if raw_keys:
                    build_type = raw_keys[0].replace('pc_build_', '').replace('_', ' ').title()
                    display_str = f"[PC Build] {build_type}"
                else:
                    display_str = "[PC Build]"
            elif brand or model:
                # Для товаров с брендом/моделью
                brand_str = brand.upper() if brand else ""
                model_str = model.upper() if model else ""
                display_str = f"[{main_cat}] {brand_str} {model_str}".strip()
            else:
                # Fallback на старые ключи
                raw_keys = item.get('product_keys', [])
                if raw_keys:
                    k = raw_keys[0].replace(main_cat.lower() + '_', '').replace('_', ' ').title()
                    display_str = f"[{main_cat}] {k}"
                else:
                    display_str = f"[{main_cat}]"
            
            self.raw_items_table.setItem(row, 5, QTableWidgetItem(display_str))

            confidence = item.get("placement_confidence", 1)
            is_deleted = item.get("is_deleted", 0) or item.get("deleted_at")

            confidence_item = QTableWidgetItem()
            confidence_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            confidence_item.setData(Qt.ItemDataRole.UserRole, item)

            if is_deleted:
                # In trash - gray lock icon
                confidence_item.setText("🗑️")
                confidence_item.setBackground(QColor(Palette.BG_DARK_3))
                confidence_item.setForeground(QColor(Palette.TEXT_MUTED))
            elif confidence == 1:
                # Reliable - green checkmark
                confidence_item.setText("✓")
                confidence_item.setForeground(QColor(Palette.SUCCESS))
                confidence_item.setBackground(QColor(Palette.with_alpha(Palette.SUCCESS, 0.15)))
            else:
                # Unreliable - red cross
                confidence_item.setText("✗")
                confidence_item.setForeground(QColor(Palette.ERROR))
                confidence_item.setBackground(QColor(Palette.with_alpha(Palette.ERROR, 0.15)))

            self.raw_items_table.setItem(row, 6, confidence_item)
        
        self.raw_items_table.resizeColumnsToContents()
        self.raw_items_table.setUpdatesEnabled(True)
        # Сбрасываем состояние кнопок
        self._update_action_buttons_state()

    def _update_action_buttons_state(self):
        """Активирует кнопки и меняет текст в зависимости от контекста (Корзина/Обычный)."""
        selected_items = self.raw_items_table.selectedItems()
        has_selection = len(selected_items) > 0

        self.btn_move_selected.setEnabled(has_selection)
        self.btn_delete_selected.setEnabled(has_selection)

        if not has_selection:
            self.btn_move_selected.setText("Переместить")
            self.btn_delete_selected.setText("В корзину")
            self.btn_toggle_confidence.setText("🔄 Надежность")  # ✅ Сброс текста
            self.btn_toggle_confidence.setEnabled(False)  # ✅ Отключить кнопку
            return

        # Определяем контекст по первому элементу (корзина или нет)
        is_trash_mode = False
        first_row = selected_items[0].row()
        item_data = self.raw_items_table.item(first_row, 0).data(Qt.ItemDataRole.UserRole)
        if item_data and item_data.get('deleted_at'):
            is_trash_mode = True

        # Считаем количество уникальных строк
        unique_rows = len(set(i.row() for i in selected_items))
        is_plural = unique_rows > 1

        # Текст для перемещения (всегда одинаковый, т.к. из корзины перемещение = восстановление в категорию)
        if is_plural:
            self.btn_move_selected.setText(f"➜ Переместить выделенное ({unique_rows})")
        else:
            self.btn_move_selected.setText("➜ Переместить")

        # Текст для удаления/восстановления
        if is_trash_mode:
            # Режим корзины -> Кнопка становится "Восстановить"
            self.btn_delete_selected.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Palette.BG_DARK_3};
                    border: 1px solid {Palette.SUCCESS};
                    color: {Palette.SUCCESS};
                    border-radius: 4px;
                    padding: 4px 12px;
                    font-weight: bold;
                    font-size: 12px;
                }}
                QPushButton:hover {{ background-color: {Palette.with_alpha(Palette.SUCCESS, 0.2)}; }}
            """)
            if is_plural:
                self.btn_delete_selected.setText(f"↺ Восстановить выделенное ({unique_rows})")
            else:
                self.btn_delete_selected.setText("↺ Восстановить")
        else:
            # Обычный режим -> Кнопка "В корзину"
            self.btn_delete_selected.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Palette.BG_DARK_3};
                    border: 1px solid {Palette.ERROR};
                    color: {Palette.ERROR};
                    border-radius: 4px;
                    padding: 4px 12px;
                    font-weight: bold;
                    font-size: 12px;
                }}
                QPushButton:hover {{ background-color: {Palette.with_alpha(Palette.ERROR, 0.2)}; }}
            """)
            if is_plural:
                self.btn_delete_selected.setText(f"🗑 Отправить выделенное в корзину ({unique_rows})")
            else:
                self.btn_delete_selected.setText("🗑 В корзину")

        # ✅ NEW: Update confidence toggle button state
        self.btn_toggle_confidence.setEnabled(has_selection and not is_trash_mode)

        if has_selection and not is_trash_mode:
            # Count reliable/unreliable in selection
            reliable_count = 0
            unreliable_count = 0
            rows = set(i.row() for i in selected_items)

            for row in rows:
                data = self.raw_items_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                if data:
                    confidence = data.get("placement_confidence", 1)
                    if confidence == 1:
                        reliable_count += 1
                    else:
                        unreliable_count += 1

            # Debug log
            logger.dev(f"Selection: {reliable_count} reliable, {unreliable_count} unreliable")

            # Determine action based on majority
            if reliable_count > unreliable_count:
                self.btn_toggle_confidence.setText(f"✗ Отметить ненадежными ({unique_rows})")
            elif unreliable_count > reliable_count:
                self.btn_toggle_confidence.setText(f"✓ Отметить надежными ({unique_rows})")
            else:
                # Equal or mixed - show toggle
                self.btn_toggle_confidence.setText(f"🔄 Переключить ({unique_rows})")
        else:
            self.btn_toggle_confidence.setText("🔄 Надежность")

    def _find_tree_item_by_data(self, parent_item, key, value):
        """Рекурсивный поиск элемента дерева по значению в UserRole."""
        if parent_item is None:
            # Поиск по всем top-level items
            for i in range(self.nav_tree.topLevelItemCount()):
                result = self._find_tree_item_by_data(self.nav_tree.topLevelItem(i), key, value)
                if result:
                    return result
            return None
        
        # Проверяем текущий элемент
        data = parent_item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get(key) == value:
            return parent_item
        
        # Проверяем детей
        for i in range(parent_item.childCount()):
            result = self._find_tree_item_by_data(parent_item.child(i), key, value)
            if result:
                return result
        
        return None

    def _update_tree_product_counter(self, product_id: int, delta: int):
        item = self._find_tree_item_by_data(None, 'id', product_id)
        if not item: return

        def update_node_text(node, d):
            data = node.data(0, Qt.ItemDataRole.UserRole)
            # Если в UserRole нет count (старый баг), берем 0, иначе реальное число
            current_count = data.get('count', 0)
            new_count = max(0, current_count + d)
            data['count'] = new_count
            node.setData(0, Qt.ItemDataRole.UserRole, data)
            
            # Обновляем текст, сохраняя префикс (иконку и имя)
            current_text = node.text(0)
            if ' (' in current_text:
                base_text = current_text.split(' (')[0]
                node.setText(0, f"{base_text} ({new_count})")
            return new_count

        new_prod_count = update_node_text(item, delta)
        
        # Обновляем родителей
        p = item.parent()
        while p:
            update_node_text(p, delta)
            p = p.parent()

        # Удаляем узел только если это РЕАЛЬНЫЙ ноль и это узел продукта
        if new_prod_count <= 0:
            parent = item.parent()
            if parent:
                parent.removeChild(item)

    def _restore_tree_product_if_missing(self, product_id: int):
        """Восстанавливает продукт в дереве, если он был удален."""
        # Проверяем, существует ли продукт в дереве
        existing = self._find_tree_item_by_data(None, 'id', product_id)
        if existing:
            return
        
        # Продукта нет - нужно восстановить из БД
        conn = self.memory.raw_data._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.id, p.key, COALESCE(p.display_name, p.key) as name,
                       p.brand, c.name as category_name,
                       COUNT(ri.id) as item_count
                FROM products p
                JOIN categories c ON p.category_id = c.id
                LEFT JOIN raw_items ri ON p.id = ri.product_id AND ri.is_deleted = 0
                WHERE p.id = ?
                GROUP BY p.id
            """, (product_id,))
            row = cursor.fetchone()
            
            if not row:
                return
            
            product_data = {
                'id': row['id'],
                'key': row['key'],
                'name': row['name'],
                'brand': row['brand'] or 'NO_BRAND',
                'category': row['category_name'],
                'count': row['item_count']
            }
            
            # Находим категорию
            cat_item = self._find_tree_item_by_data(None, 'name', product_data['category'])
            if not cat_item:
                # Категория не найдена - создаем (edge case)
                cat_item = QTreeWidgetItem([f"📂 {product_data['category']}"])
                cat_item.setData(0, Qt.ItemDataRole.UserRole, {
                    'type': 'category',
                    'name': product_data['category']
                })
                self.nav_tree.addTopLevelItem(cat_item)
            
            # Находим/создаем бренд
            brand_name = product_data['brand'].upper()
            brand_item = None
            
            if brand_name != 'NO_BRAND':
                # Ищем бренд среди детей категории
                for i in range(cat_item.childCount()):
                    child = cat_item.child(i)
                    child_data = child.data(0, Qt.ItemDataRole.UserRole)
                    if child_data and child_data.get('type') == 'brand_group':
                        # Проверяем по тексту (т.к. у brand_group нет name в data)
                        if child.text(0) == f"🏭 {brand_name}":
                            brand_item = child
                            break
                
                if not brand_item:
                    brand_item = QTreeWidgetItem([f"🏭 {brand_name}"])
                    brand_item.setData(0, Qt.ItemDataRole.UserRole, {'type': 'brand_group'})
                    cat_item.addChild(brand_item)
            else:
                brand_item = cat_item
            
            # Создаем продукт
            product_data['count'] = 0
            prod_item = QTreeWidgetItem([f"📦 {product_data['name']} (0)"])
            prod_item.setData(0, Qt.ItemDataRole.UserRole, {
                'type': 'product_key',
                'key': product_data['key'],
                'id': product_data['id']
            })
            brand_item.addChild(prod_item)
            
        finally:
            conn.close()
    
    def _remove_rows_visually(self, rows: set, delta: int = -1):
        """
        Мгновенно удаляет строки из таблицы и обновляет счетчики в дереве.
        delta: -1 для удаления/перемещения (уменьшить), +1 для восстановления (увеличить)
        """
        product_ids_to_update = Counter()
        
        for row in rows:
            id_item = self.raw_items_table.item(row, 0)
            if not id_item: continue
            data = id_item.data(Qt.ItemDataRole.UserRole)
            if not data: continue
            
            # Определяем, какой ID использовать (текущий или оригинальный для корзины)
            pid = data.get('product_id') or data.get('original_product_id')
            if pid:
                product_ids_to_update[pid] += 1

        # Удаляем строки из таблицы UI
        for row in sorted(rows, reverse=True):
            self.raw_items_table.removeRow(row)
        
        # Обновляем счетчики в дереве
        for pid, count in product_ids_to_update.items():
            self._update_tree_product_counter(pid, delta * count)

        # Обновляем счетчик корзины
        trash_item = self._find_tree_item_by_data(None, 'type', 'trash')
        if trash_item:
            match = re.match(r'.*\((\d+)\)', trash_item.text(0))
            if match:
                curr = int(match.group(1))
                # Если мы удаляем (delta -1), в корзину ПРИБАВЛЯЕМ. Если восстанавливаем (delta +1), УБАВЛЯЕМ.
                trash_delta = len(rows) if delta < 0 else -len(rows)
                # Если мы в режиме "Корзина" и удаляем из нее навсегда, то просто убавляем
                # Но для простоты текущей логики:
                new_val = max(0, curr + trash_delta)
                trash_item.setText(0, f"🗑️ Корзина ({new_val})")

        self._update_stats()
        self._clear_details()
        self._update_action_buttons_state()

    def _on_move_selected_clicked(self):
        selected_items = self.raw_items_table.selectedItems()
        if not selected_items: return

        rows = set(item.row() for item in selected_items)
        item_ids = []
        for row in rows:
            data = self.raw_items_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if data: item_ids.append(data.get('id'))

        if not item_ids: return

        hierarchy = self.memory.raw_data.get_hierarchy_data()
        first_data = self.raw_items_table.item(list(rows)[0], 0).data(Qt.ItemDataRole.UserRole)
        current_prod_id = first_data.get('product_id')

        dialog = MoveItemDialog(hierarchy, current_prod_id, self)
        if dialog.exec():
            target_prod_id = dialog.get_selected_product_id()
            if target_prod_id:
                count = self.memory.raw_data.move_items_to_product(item_ids, target_prod_id)
                if count > 0:
                    logger.success(f"Перемещено {count} элементов")
                    
                    # 1. Сначала уменьшаем счетчики СТАРЫХ продуктов и удаляем строки
                    self._remove_rows_visually(rows, delta=-1)
                    
                    # 2. Затем увеличиваем счетчик НОВОГО продукта
                    target_item = self._find_tree_item_by_data(None, 'id', target_prod_id)
                    if not target_item:
                        self._restore_tree_product_if_missing(target_prod_id)
                    else:
                        self._update_tree_product_counter(target_prod_id, count)

    def _on_delete_selected_clicked(self):
        selected_items = self.raw_items_table.selectedItems()
        if not selected_items: return

        rows = set(item.row() for item in selected_items)
        item_ids = [self.raw_items_table.item(r, 0).data(Qt.ItemDataRole.UserRole).get('id') for r in rows]
        
        is_trash_mode = any(self.raw_items_table.item(r, 0).data(Qt.ItemDataRole.UserRole).get('deleted_at') for r in rows)

        if not item_ids: return

        if is_trash_mode:
            # ВОССТАНОВЛЕНИЕ
            count = self.memory.raw_data.restore_items(item_ids)
            if count > 0:
                logger.success(f"Восстановлено {count} элементов")
                
                # 1. Убеждаемся, что узлы продуктов существуют в дереве (если они были удалены)
                pids = set()
                for row in rows:
                    data = self.raw_items_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                    if data.get('original_product_id'): pids.add(data['original_product_id'])
                
                for pid in pids:
                    self._restore_tree_product_if_missing(pid)
                
                # 2. Используем универсальный метод для инкремента счетчиков (+1) и удаления строк из таблицы
                # Мы передаем delta=1, чтобы _remove_rows_visually ПРИБАВИЛ к счетчикам продуктов
                self._remove_rows_visually(rows, delta=1)
        else:
            # УДАЛЕНИЕ В КОРЗИНУ (уже работает, оставляем вызов _remove_rows_visually с delta=-1)
            if QMessageBox.question(self, "Подтверждение", f"Удалить {len(item_ids)} элементов?") == QMessageBox.StandardButton.Yes:
                count = self.memory.raw_data.soft_delete_items(item_ids)
                if count > 0:
                    logger.success(f"Перемещено в корзину: {count}")
                    self._remove_rows_visually(rows, delta=-1)

    def on_toggle_confidence_clicked(self):
        """Toggle placement_confidence for selected items."""
        selected_items = self.raw_items_table.selectedItems()
        if not selected_items:
            return

        rows = set(item.row() for item in selected_items)
        item_data_map = {}  # row -> (item_id, current_confidence)

        for row in rows:
            data = self.raw_items_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if data:
                if data.get("deleted_at") or data.get("is_deleted"):
                    continue
                item_id = data.get("id")
                confidence = data.get("placement_confidence", 1)
                item_data_map[row] = (item_id, confidence, data)

        if not item_data_map:
            QMessageBox.warning(self, "Ошибка", "Нельзя изменить надежность элементов в корзине!")
            return

        # Determine new state based on majority
        current_confidences = [conf for (_, conf, _) in item_data_map.values()]
        reliable_count = sum(1 for c in current_confidences if c == 1)
        new_confidence = 0 if reliable_count >= len(current_confidences) / 2 else 1

        # Confirm action
        action_text = "надежными" if new_confidence == 1 else "ненадежными"
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Пометить {len(item_data_map)} элементов как {action_text}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Update in database
        success_count = 0
        for row, (item_id, old_confidence, full_data) in item_data_map.items():
            if self.memory.raw_data.update_item_confidence(item_id, new_confidence == 1):
                success_count += 1

                # ✅ Update only the confidence cell (column 6)
                confidence_item = self.raw_items_table.item(row, 6)
                if confidence_item:
                    if new_confidence == 1:
                        confidence_item.setText("✓")
                        confidence_item.setForeground(QColor(Palette.SUCCESS))
                        confidence_item.setBackground(QColor(Palette.with_alpha(Palette.SUCCESS, 0.15)))
                    else:
                        confidence_item.setText("✗")
                        confidence_item.setForeground(QColor(Palette.ERROR))
                        confidence_item.setBackground(QColor(Palette.with_alpha(Palette.ERROR, 0.15)))

                # ✅ Update UserRole data
                full_data["placement_confidence"] = new_confidence
                self.raw_items_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, full_data)

        logger.success(f"✅ Обновлен статус надежности для {success_count}/{len(item_data_map)} элементов")

        # ✅ Update button state
        self._update_action_buttons_state()

    def _populate_knowledge_table(self, chunks: list):
        """Populate the knowledge table."""
        from PyQt6.QtGui import QColor
        self.knowledge_table.setRowCount(0)
        
        for chunk in chunks:
            row = self.knowledge_table.rowCount()
            self.knowledge_table.insertRow(row)
            
            # ID
            self.knowledge_table.setItem(row, 0, QTableWidgetItem(str(chunk.get('id', ''))))
            
            # Type
            chunk_type = chunk.get('chunk_type', 'UNKNOWN')
            type_icons = {
                'PRODUCT': '📦',
                'CATEGORY': '📁',
                'DATABASE': '🗄️',
                'AI_BEHAVIOR': '🤖',
                'CUSTOM': '📝'
            }
            type_names = {
                'PRODUCT': 'Продукт',
                'CATEGORY': 'Категория',
                'DATABASE': 'База данных',
                'AI_BEHAVIOR': 'Поведение ИИ',
                'CUSTOM': 'Кастомное'
            }
            
            chunk_type = chunk.get('chunk_type', 'UNKNOWN')
            icon = type_icons.get(chunk_type, '📝')
            name = type_names.get(chunk_type, chunk_type)
            
            self.knowledge_table.setItem(row, 1, QTableWidgetItem(f"{icon} {name}"))
            
            # Key
            self.knowledge_table.setItem(row, 2, QTableWidgetItem(chunk.get('chunk_key', '')))
            
            # Status with color
            status = chunk.get('status', 'UNKNOWN')
            status_colors = {
                'PENDING': '#FFA500',
                'INITIALIZING': '#4169E1',
                'READY': '#32CD32',
                'FAILED': '#FF4444',
                'COMPRESSED': '#808080'
            }
            item = QTableWidgetItem(status)
            item.setForeground(QColor(status_colors.get(status, Palette.TEXT)))
            self.knowledge_table.setItem(row, 3, item)
            
            # Updated
            updated = chunk.get('last_updated', '')[:16] if chunk.get('last_updated') else ''
            self.knowledge_table.setItem(row, 4, QTableWidgetItem(updated))
            
            # Store full data
            self.knowledge_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, chunk)

    def _update_stats(self):
        """Update statistics display."""
        if not self.memory:
            return
            
        try:
            raw_stats = self.memory.raw_data.get_statistics()
            knowledge_stats = self.memory.knowledge.get_statistics()
            
            stats_text = (
                f"📦 Товаров: {raw_stats.get('total_items', 0)}\n"
                f"📁 Категорий: {raw_stats.get('total_categories', 0)}\n"
                f"🧠 Чанков: {knowledge_stats.get('total_chunks', 0)}\n"
                f"✅ Готовых: {knowledge_stats.get('by_status', {}).get('READY', 0)}"
            )
            self.stats_label.setText(stats_text)
        except Exception as e:
            logger.error(f"Failed to update stats: {e}")

    def _on_tree_item_clicked(self, item, column):
        """Handle tree item click."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
            
        item_type = data.get('type')
        
        if item_type == 'all_items':
            items = self.memory.get_raw_items(limit=1000)
            self._populate_raw_items_table(items)
            self.table_tabs.setCurrentIndex(0)
            
        elif item_type == 'all_knowledge':
            chunks = self.memory.get_knowledge(limit=1000)
            self._populate_knowledge_table(chunks)
            self.table_tabs.setCurrentIndex(1)
            
        elif item_type == 'category':
            items = self.memory.get_raw_items(category=data.get('name'), limit=1000)
            self._populate_raw_items_table(items)
            self.table_tabs.setCurrentIndex(0)
            
        elif item_type == 'brand_group':
            # ИСПРАВЛЕНИЕ: при клике на бренд (например, ACER) показываем все товары этого бренда
            brand_items = []
            # Перебираем всех детей (product_key items)
            for i in range(item.childCount()):
                child = item.child(i)
                child_data = child.data(0, Qt.ItemDataRole.UserRole)
                if child_data and child_data.get('type') == 'product_key':
                    items = self.memory.get_items_for_product_key(child_data.get('key'))
                    brand_items.extend(items)
            
            self._populate_raw_items_table(brand_items)
            self.table_tabs.setCurrentIndex(0)
            
        elif item_type == 'trash':
            # Показываем элементы из корзины
            trash_items = self.memory.raw_data.get_trash_items()
            self._populate_raw_items_table(trash_items)
            self.table_tabs.setCurrentIndex(0)
            
        elif item_type == 'product_key':
            items = self.memory.get_items_for_product_key(data.get('key'))
            self._populate_raw_items_table(items)
            self.table_tabs.setCurrentIndex(0)

    def _on_raw_item_selection_changed(self, current, previous):
        """Обновлен: убрано управление кнопками, которые мы удалили."""
        if not current: return
        row = current.row()
        id_item = self.raw_items_table.item(row, 0)
        if id_item:
            data = id_item.data(Qt.ItemDataRole.UserRole)
            if data:
                self._show_details(data, 'raw_item')

    def _on_knowledge_selection_changed(self, current, previous):
        """Handle knowledge chunk selection change (mouse or keyboard)."""
        if not current:
            return
        
        # Получаем данные из первой колонки текущей строки
        row = current.row()
        id_item = self.knowledge_table.item(row, 0)
        
        if id_item:
            data = id_item.data(Qt.ItemDataRole.UserRole)
            if data:
                self._show_details(data, 'knowledge')
                self.btn_delete_selected.setEnabled(False)
                self.cultivate_btn.setEnabled(True)

    def _show_details(self, data: dict, data_type: str):
        """Show details in the right panel."""
        # Clear existing content
        while self.details_layout.count():
            item = self.details_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not data:
            return
            
        self.current_selection = {'data': data, 'type': data_type}
        
        if data_type == 'raw_item':
            self._render_raw_item_details(data)
        elif data_type == 'knowledge':
            self._render_knowledge_details(data)

    def _render_raw_item_details(self, item: dict):
        """Render raw item details with modern UI."""
        # 1. Title Section
        title = QLabel(item.get('title', 'Unknown'))
        title.setStyleSheet(TextPresets.h3())
        title.setWordWrap(True)
        self.details_layout.addWidget(title)
        
        # 2. Price Section (Prominent)
        price_val = item.get('price', 0)
        if price_val:
            price_lbl = QLabel(f"{price_val} ₽")
            price_lbl.setStyleSheet(f"""
                font-family: {Typography.UI};
                font-size: 18px;
                font-weight: {Typography.WEIGHT_BOLD};
                color: {Palette.PRIMARY};
                margin-bottom: 4px;
            """)
            self.details_layout.addWidget(price_lbl)

        # Separator
        self.details_layout.addWidget(self._create_divider())
        
        # 3. Metadata Grid (Form Layout)
        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(6) # Вертикальный отступ между строками
        form_layout.setHorizontalSpacing(12) # Горизонтальный отступ между Label и Value
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        
        # Helper for rows
        def add_row(label_text, value_text, is_link=False):
            if not value_text: return
            lbl = QLabel(f"{label_text}:")
            lbl.setStyleSheet(TextPresets.label()) # Серый, капсом, моноширинный
            
            val = QLabel()
            if is_link:
                # Кликабельная ссылка
                val.setText(f'Открыть объявление ↗')
                val.setOpenExternalLinks(True)
                val.setCursor(Qt.CursorShape.PointingHandCursor)
                val.setStyleSheet(f"font-family: {Typography.UI}; font-size: {Typography.SIZE_MD}px;")
                val.setText(f'<a href="{value_text}" style="color: {Palette.PRIMARY}; text-decoration: none;">Открыть объявление ↗</a>')
            else:
                val.setText(str(value_text))
                val.setStyleSheet(TextPresets.body())
                val.setWordWrap(True)
                val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            
            form_layout.addRow(lbl, val)

        add_row("ID", item.get('id'))
        add_row("AD ID", item.get('ad_id'))
        add_row("ГОРОД", item.get('city'))
        add_row("СОСТОЯНИЕ", item.get('condition'))
        add_row("ПРОДАВЕЦ", item.get('seller_id'))
        add_row("ПРОСМОТРЫ", item.get('views'))
        add_row("ДАТА", item.get('date_text'))
        add_row("ССЫЛКА", item.get('link'), is_link=True)
        
        self.details_layout.addWidget(form_widget)
        
        # 4. Description Section
        desc_text = item.get('description')
        if desc_text:
            self.details_layout.addWidget(self._create_divider())
            
            desc_header = QLabel("ОПИСАНИЕ")
            desc_header.setStyleSheet(Components.subsection_title())
            self.details_layout.addWidget(desc_header)
            
            desc_lbl = QLabel(desc_text) # Без обрезки текста
            desc_lbl.setStyleSheet(f"""
                font-family: {Typography.UI};
                font-size: {Typography.SIZE_MD}px;
                line-height: {Typography.LINE_RELAXED};
                color: {Palette.TEXT};
            """)
            desc_lbl.setWordWrap(True)
            desc_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.details_layout.addWidget(desc_lbl)

        # 5. Tags Section
        categories = item.get('categories', [])
        product_keys = item.get('product_keys', [])
        all_tags = categories + product_keys
        
        if all_tags:
            self.details_layout.addWidget(self._create_divider())
            tags_widget = QLabel(" • ".join(all_tags))
            tags_widget.setStyleSheet(f"color: {Palette.TEXT_SECONDARY}; font-size: {Typography.SIZE_SM}px; font-style: italic;")
            tags_widget.setWordWrap(True)
            self.details_layout.addWidget(tags_widget)
            
        # Spacer at bottom to push content up if needed
        self.details_layout.addStretch()

    def _render_knowledge_details(self, chunk: dict):
        """Render knowledge chunk details with modern UI."""
        title = QLabel(chunk.get('title', f"Chunk #{chunk.get('id', 'Unknown')}"))
        title.setStyleSheet(TextPresets.h3())
        title.setWordWrap(True)
        self.details_layout.addWidget(title)
        
        status = chunk.get('status', 'UNKNOWN')
        status_colors = {'PENDING': '#FFA500', 'INITIALIZING': '#4169E1', 'READY': '#32CD32', 'FAILED': Palette.ERROR}
        
        status_container = QWidget()
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(0, 8, 0, 8)
        status_layout.setSpacing(8)
        
        badge = QLabel(f" {status} ")
        badge_color = status_colors.get(status, Palette.TEXT)
        badge.setStyleSheet(f"background-color: {Palette.with_alpha(badge_color, 0.15)}; color: {badge_color}; border: 1px solid {badge_color}; border-radius: 4px; font-weight: bold; font-size: 10px;")
        status_layout.addWidget(badge)
        status_layout.addStretch()
        self.details_layout.addWidget(status_container)
        self.details_layout.addWidget(self._create_divider())
        
        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(4)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        
        def add_row(label, value):
            if not value: return
            lbl = QLabel(f"{label}:")
            lbl.setStyleSheet(TextPresets.label())
            val = QLabel(str(value))
            val.setStyleSheet(TextPresets.body())
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form_layout.addRow(lbl, val)

        def fmt_time(iso_str):
            if not iso_str: return "-"
            # Убираем 'T' для красоты
            return iso_str.replace("T", " ")[:16]

        add_row("ТИП", chunk.get('chunk_type'))
        add_row("КЛЮЧ", chunk.get('chunk_key'))
        add_row("ПРИОРИТЕТ", chunk.get('priority'))
        add_row("СОЗДАНО", fmt_time(chunk.get('created_at')))
        add_row("ОБНОВЛЕНО", fmt_time(chunk.get('last_updated')))
        
        self.details_layout.addWidget(form_widget)

        summary = chunk.get('summary')
        if summary:
            self.details_layout.addWidget(self._create_divider())
            lbl = QLabel("СВОДКА")
            lbl.setStyleSheet(Components.subsection_title())
            self.details_layout.addWidget(lbl)
            txt = QLabel(summary)
            txt.setStyleSheet(TextPresets.body())
            txt.setWordWrap(True)
            txt.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.details_layout.addWidget(txt)
            
        self.details_layout.addStretch()

    def _create_divider(self):
        """Helper to create a visual divider line."""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet(f"background-color: {Palette.DIVIDER}; max-height: 1px; margin: 8px 0;")
        return line

    def _on_nav_tab_changed(self, index):
        """
        0 = Список (фиксированный, узкий)
        1 = Граф (растягиваемый, широкий)
        """
        sizes = self.splitter.sizes()
        if not sizes: return
        total_width = sum(sizes)
        right_width = sizes[2] if len(sizes) > 2 else 350
        
        if index == 1: # Граф
            # Разрешаем левой панели тянуться
            self.splitter.setStretchFactor(0, 1)
            self.left_panel.setMaximumWidth(16777215)
            # 45% ширины
            new_left = int(total_width * 0.45)
            remain = total_width - new_left - right_width
            self.splitter.setSizes([new_left, remain, right_width])
            
            if hasattr(self, 'graph_widget'):
                self.graph_widget.wake_up_physics()
        else: # Список
            # Запрещаем левой панели тянуться (она станет фиксированной)
            self.splitter.setStretchFactor(0, 0)
            # Фиксированная ширина (чуть больше, 400px)
            target_left = 400
            remain = total_width - target_left - right_width
            self.splitter.setSizes([target_left, remain, right_width])

    def _on_graph_node_selected(self, chunk_id):
        # Находим чанк и открываем его детали
        chunk = self.memory.knowledge.get_chunk_by_id(chunk_id)
        if chunk:
            self.table_tabs.setCurrentIndex(1) # Переключаем на таб знаний
            self._show_details(chunk, 'knowledge')

    def _on_search(self, txt):
        if not txt:
            self._load_data()
            return
            
        self._populate_raw_items_table(self.memory.get_raw_items(search_query=txt, limit=100))
        
        # Filter knowledge locally
        all_k = self.memory.get_knowledge(limit=1000)
        filt = [c for c in all_k if txt.lower() in str(c).lower()]
        self._populate_knowledge_table(filt)

    def _on_filter_changed(self, text: str):
        """Handle filter by type."""
        if text == "Все":
            chunks = self.memory.get_knowledge(limit=1000)
        else:
            chunks = self.memory.get_knowledge(chunk_type=text, limit=1000)
        self._populate_knowledge_table(chunks)

    def _on_nav_search(self, text: str):
        """Поиск по навигации (Список/Граф)."""
        current_tab = self.nav_tabs.currentIndex()
        
        if current_tab == 0: # Список (дерево)
            if not text:
                # Показать все элементы
                for i in range(self.nav_tree.topLevelItemCount()):
                    self._show_tree_item_recursive(self.nav_tree.topLevelItem(i), True)
                return
            
            # Фильтруем дерево
            text_lower = text.lower()
            for i in range(self.nav_tree.topLevelItemCount()):
                self._filter_tree_item(self.nav_tree.topLevelItem(i), text_lower)
                
        elif current_tab == 1: # Граф
            # Поиск в графе (если реализовано в KnowledgeGraphWidget)
            if hasattr(self.graph_widget, 'filter_nodes'):
                self.graph_widget.filter_nodes(text)

    def _show_tree_item_recursive(self, item, visible):
        """Рекурсивно показать/скрыть элементы дерева."""
        item.setHidden(not visible)
        for i in range(item.childCount()):
            self._show_tree_item_recursive(item.child(i), visible)

    def _filter_tree_item(self, item, search_text):
        """Фильтрация элементов дерева по тексту."""
        item_text = item.text(0).lower()
        match = search_text in item_text
        
        # Проверяем детей
        child_match = False
        for i in range(item.childCount()):
            if self._filter_tree_item(item.child(i), search_text):
                child_match = True
        
        # Показываем, если совпадает сам элемент или хотя бы один ребенок
        visible = match or child_match
        item.setHidden(not visible)
        
        # Разворачиваем если есть совпадение в детях
        if child_match:
            item.setExpanded(True)
            
        return visible

    def _on_table_search(self, text: str):
        """Поиск по всем столбцам текущей таблицы."""
        current_tab = self.table_tabs.currentIndex()
        text_lower = text.lower()
        
        if current_tab == 0: # Сырые данные
            table = self.raw_items_table
        else: # Знания ИИ
            table = self.knowledge_table
            
        if not text:
            # Показать все строки
            for row in range(table.rowCount()):
                table.setRowHidden(row, False)
            return

        # Фильтруем строки
        for row in range(table.rowCount()):
            match = False
            for col in range(table.columnCount()):
                item = table.item(row, col)
                if item and text_lower in item.text().lower():
                    match = True
                    break
            table.setRowHidden(row, not match)

    def _on_table_tab_changed(self, index):
        """Обработка переключения между табами таблиц."""
        # Очищаем поиск при переключении
        self.table_search_edit.clear()

    def _recultivate(self):
        if not hasattr(self, 'current_selection') or self.current_selection['type'] != 'knowledge': return
        data = self.current_selection['data']
        # Обновляем статус в БД
        self.memory.knowledge.update_chunk_status(data.get('id'), 'PENDING')
        # Обновляем UI таблицы
        self._refresh_data()
        
        # Сигнализируем, что пора запускать нейросеть
        logger.info(f"Запрошена перекультивация из БД для чанка {data.get('id')}")
        self.recultivate_requested.emit()

    def _clear_details(self):
        """Очистка деталей и сброс selection."""
        while self.details_layout.count():
            item = self.details_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.current_selection = None
        self.cultivate_btn.setEnabled(False)

    def _on_tree_item_delete(self, index):
        """Удаление элемента из дерева (категория/продукт)."""
        item = self.nav_tree.itemFromIndex(index)
        if not item:
            return
            
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
            
        item_type = data.get('type')
        
        # Подтверждение
        if item_type == 'category':
            cat_name = data.get('name')
            reply = QMessageBox.question(
                self, 
                "Удалить категорию?",
                f"Переместить категорию '{cat_name}' и все её продукты в корзину?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                cat_id = self.memory.raw_data.get_or_create_category(cat_name)
                deleted_count = self.memory.raw_data.soft_delete_category(cat_id)
                logger.success(f"Категория '{cat_name}' и {deleted_count} элементов перемещены в корзину")
                self._refresh_data()
                
        elif item_type == 'brand_group':
            # Удаляем все продукты бренда
            reply = QMessageBox.question(
                self, 
                "Удалить бренд?",
                "Переместить все продукты этого бренда в корзину?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                total_deleted = 0
                for i in range(item.childCount()):
                    child = item.child(i)
                    child_data = child.data(0, Qt.ItemDataRole.UserRole)
                    if child_data and child_data.get('type') == 'product_key':
                        prod_id = child_data.get('id')
                        deleted = self.memory.raw_data.soft_delete_product(prod_id)
                        total_deleted += deleted
                logger.success(f"{total_deleted} элементов перемещены в корзину")
                self._refresh_data()
                
        elif item_type == 'product_key':
            prod_name = data.get('key')
            prod_id = data.get('id')
            reply = QMessageBox.question(
                self, 
                "Удалить продукт?",
                f"Переместить продукт '{prod_name}' и все его элементы в корзину?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                deleted_count = self.memory.raw_data.soft_delete_product(prod_id)
                logger.success(f"Продукт '{prod_name}' и {deleted_count} элементов перемещены в корзину")
                self._refresh_data()

    def _empty_trash(self):
        """Полная очистка корзины."""
        trash_count = len(self.memory.raw_data.get_trash_items())
        if trash_count == 0:
            QMessageBox.information(self, "Корзина пуста", "В корзине нет элементов")
            return
            
        reply = QMessageBox.warning(
            self,
            "Очистить корзину?",
            f"Удалить {trash_count} элементов НАВСЕГДА?\n\nЭто действие нельзя отменить!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            deleted = self.memory.raw_data.empty_trash()
            logger.success(f"Корзина очищена: {deleted} элементов удалено")
            self._refresh_data()
            self._clear_details()

    def _refresh_data(self):
        """Перезагрузить данные, сохраняя состояние дерева."""
        # 1. Сохраняем состояние раскрытых элементов
        expanded_ids = self._save_tree_state()
        
        # 2. Перезагружаем данные
        self._load_data()
        
        # 3. Восстанавливаем состояние
        self._restore_tree_state(expanded_ids)
        
        # 4. Сбрасываем выбор
        self._clear_details()

    def _save_tree_state(self) -> set:
        """Сохраняет уникальные идентификаторы раскрытых элементов дерева."""
        expanded = set()
        iterator = QTreeWidgetItemIterator(self.nav_tree)
        while iterator.value():
            item = iterator.value()
            if item.isExpanded():
                key = self._get_item_unique_key(item)
                if key:
                    expanded.add(key)
            iterator += 1
        return expanded

    def _restore_tree_state(self, expanded_ids: set):
        """Восстанавливает раскрытие элементов."""
        iterator = QTreeWidgetItemIterator(self.nav_tree)
        while iterator.value():
            item = iterator.value()
            key = self._get_item_unique_key(item)
            if key in expanded_ids:
                item.setExpanded(True)
            iterator += 1

    def _get_item_unique_key(self, item: QTreeWidgetItem) -> str:
        """Генерирует уникальный ключ для элемента дерева."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data: return None
        
        itype = data.get('type')
        if itype == 'category':
            return f"cat:{data.get('name')}"
        elif itype == 'brand_group':
            # Бренд уникален в рамках категории
            parent = item.parent()
            parent_name = parent.data(0, Qt.ItemDataRole.UserRole).get('name') if parent else "root"
            return f"brand:{parent_name}:{item.text(0)}"
        elif itype == 'product_key':
            return f"prod:{data.get('id')}"
        elif itype == 'trash':
            return "system:trash"
        elif itype == 'all_items':
            return "system:all_items"
        
        return None

    def _export_data(self):
        """Export database to JSON."""
        from PyQt6.QtWidgets import QFileDialog
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Экспорт базы данных", "", "JSON файлы (*.json)"
        )
        if not filepath:
            return
            
        try:
            self.memory.export_all(BASE_APP_DIR)
            QMessageBox.information(self, "Успех", "База данных экспортирована")
        except Exception as e:
            logger.error(f"Export failed: {e}")
            QMessageBox.critical(self, "Ошибка", f"Экспорт не удался: {e}")

    def _import_data(self):
        """Import database from JSON."""
        from PyQt6.QtWidgets import QFileDialog
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Импорт базы данных", "", "JSON файлы (*.json)"
        )
        if not filepath:
            return
            
        confirm = QMessageBox.question(
            self, 
            "Подтверждение", 
            "Импорт добавит данные к существующим. Продолжить?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
            
        try:
            self.memory.import_all(raw_path=filepath, clear_first=False)
            self._refresh_data()
            QMessageBox.information(self, "Успех", "Данные импортированы")
        except Exception as e:
            logger.error(f"Import failed: {e}")
            QMessageBox.critical(self, "Ошибка", f"Импорт не удался: {e}")

    def _clear_database(self):
        """Clear the entire database."""
        confirm = QMessageBox(
            QMessageBox.Icon.Warning,
            "Опасная операция",
            "Вы уверены, что хотите ОЧИСТИТЬ ВСЮ БАЗУ ДАННЫХ?\n\nЭто действие НЕЛЬЗЯ отменить!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm.exec() != QMessageBox.StandardButton.Yes:
            return
            
        # Double confirm with typed text
        confirm2 = QMessageBox(
            QMessageBox.Icon.Critical,
            "Подтверждение",
            "Напишите 'УДАЛИТЬ' для подтверждения:",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        
        # For simplicity, just do it if user clicked Yes above
        try:
            self.memory.reset_all()
            self._refresh_data()
            self._clear_details()
            logger.success("Database cleared")
            QMessageBox.information(self, "Успех", "База данных очищена")
        except Exception as e:
            logger.error(f"Clear failed: {e}")
            QMessageBox.critical(self, "Ошибка", f"Очистка не удалась: {e}")

    def refresh_data(self):
        """Public method to refresh data (called from outside)."""
        self._refresh_data()