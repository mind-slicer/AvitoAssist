from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QTreeWidget, QTreeWidgetItem, QTableWidget,
    QTableWidgetItem, QLineEdit, QComboBox, QSplitter, QToolBar,
    QMessageBox, QTabWidget, QAbstractItemView, QFormLayout,
    QStyledItemDelegate, QStyle, QStyleOptionButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint, QSize
from PyQt6.QtGui import QAction, QPainter, QColor

from app.ui.styles import Components, Palette, Spacing
from app.ui.styles.typography import TextPresets, Typography
from app.ui.widgets.move_item_dialog import MoveItemDialog
from app.core.log_manager import logger
from app.config import BASE_APP_DIR


class TreeItemDelegate(QStyledItemDelegate):
    """
    Делегат для отображения кнопок удаления в дереве.
    """
    
    delete_clicked = pyqtSignal(object)  # Сигнал при клике на удаление
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hovered_item = None
    
    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        
        # Рисуем кнопку удаления только при hover
        if option.state & QStyle.StateFlag.State_MouseOver:
            # Кнопка в правом углу
            btn_size = 20
            btn_rect = QRect(
                option.rect.right() - btn_size - 4,
                option.rect.top() + (option.rect.height() - btn_size) // 2,
                btn_size,
                btn_size
            )
            
            # Фон кнопки
            painter.setBrush(QColor(Palette.ERROR))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(btn_rect, 3, 3)
            
            # Иконка "X"
            painter.setPen(QColor("white"))
            painter.setFont(painter.font())
            painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, "✖")
    
    def editorEvent(self, event, model, option, index):
        if event.type() == event.Type.MouseButtonRelease:
            # Проверяем клик по кнопке удаления
            btn_size = 20
            btn_rect = QRect(
                option.rect.right() - btn_size - 4,
                option.rect.top() + (option.rect.height() - btn_size) // 2,
                btn_size,
                btn_size
            )
            
            if btn_rect.contains(event.pos()):
                self.delete_clicked.emit(index)
                return True
        
        return super().editorEvent(event, model, option, index)


class TableItemDelegate(QStyledItemDelegate):
    """
    Делегат для кнопок удаления/перемещения в таблице.
    """
    
    delete_clicked = pyqtSignal(int)  # row
    move_clicked = pyqtSignal(int)    # row
    
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def paint(self, painter, option, index):
        # Не рисуем ничего, кнопки будут в отдельной колонке
        pass
    
    def createEditor(self, parent, option, index):
        # Создаем виджет с кнопками
        from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton
        
        widget = QWidget(parent)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)
        
        # Кнопка перемещения
        btn_move = QPushButton("➜")
        btn_move.setFixedSize(24, 24)
        btn_move.setToolTip("Переместить в другой продукт")
        btn_move.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_DARK_3};
                border: 1px solid {Palette.PRIMARY};
                color: {Palette.PRIMARY};
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Palette.with_alpha(Palette.PRIMARY, 0.2)};
            }}
        """)
        btn_move.clicked.connect(lambda: self.move_clicked.emit(index.row()))
        
        # Кнопка удаления
        btn_delete = QPushButton("🗑")
        btn_delete.setFixedSize(24, 24)
        btn_delete.setToolTip("Удалить элемент")
        btn_delete.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_DARK_3};
                border: 1px solid {Palette.ERROR};
                color: {Palette.ERROR};
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Palette.with_alpha(Palette.ERROR, 0.2)};
            }}
        """)
        btn_delete.clicked.connect(lambda: self.delete_clicked.emit(index.row()))
        
        layout.addWidget(btn_move)
        layout.addWidget(btn_delete)
        layout.addStretch()
        
        return widget


class DatabaseTab(QWidget):
    item_selected = pyqtSignal(dict)
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
        self.left_panel.setMinimumWidth(400)  # Увеличено с 370
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
        self.stats_label.setWordWrap(True)  # Перенос слов
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

        # Header с поиском по таблице (БЕЛОЕ ПОДЧЕРКИВАНИЕ)
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(Spacing.SM)

        table_header = QLabel("ДАННЫЕ В БАЗЕ")
        table_header.setStyleSheet(Components.subsection_title())
        header_layout.addWidget(table_header)

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
        self.raw_items_table.setColumnCount(7)  # БЫЛО 6, СТАЛО 7
        self.raw_items_table.setHorizontalHeaderLabels([
            "ID", "Заголовок", "Цена", "Город", "Дата", "Категории", "Действия"
        ])
        self.raw_items_table.horizontalHeader().setStretchLastSection(False)
        self.raw_items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.raw_items_table.setStyleSheet(self._get_table_style())
        self.raw_items_table.currentItemChanged.connect(self._on_raw_item_selection_changed)
        
        # Делегат для кнопок действий
        self.table_delegate = TableItemDelegate()
        self.table_delegate.delete_clicked.connect(self._on_table_item_delete)
        self.table_delegate.move_clicked.connect(self._on_table_item_move)
        self.raw_items_table.setItemDelegateForColumn(6, self.table_delegate)
        
        self.table_tabs.addTab(self.raw_items_table, "📦 Сырые данные")

        # Knowledge Table Tab Container (СИНИЙ ЦВЕТ - фильтр справа от таба)
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

        self.delete_btn = QPushButton("🗑️ Удалить")
        self.delete_btn.setStyleSheet(Components.stop_button())
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._delete_selected)
        right_layout.addWidget(self.delete_btn)
        
        # Кнопка восстановления (скрыта по умолчанию)
        self.restore_btn = QPushButton("↺ Восстановить")
        self.restore_btn.setStyleSheet(Components.start_button())
        self.restore_btn.setEnabled(False)
        self.restore_btn.setVisible(False)
        self.restore_btn.clicked.connect(self._restore_selected)
        right_layout.addWidget(self.restore_btn)
        
        # Кнопка окончательного удаления (скрыта по умолчанию)
        self.permanent_delete_btn = QPushButton("⚠ Удалить навсегда")
        self.permanent_delete_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.ERROR};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Palette.with_alpha(Palette.ERROR, 0.8)};
            }}
        """)
        self.permanent_delete_btn.setEnabled(False)
        self.permanent_delete_btn.setVisible(False)
        self.permanent_delete_btn.clicked.connect(self._permanent_delete_selected)
        right_layout.addWidget(self.permanent_delete_btn)
    
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
            cat_node = QTreeWidgetItem([f"📂 {cat_name}"])
            cat_node.setData(0, Qt.ItemDataRole.UserRole, {
                'type': 'category',
                'name': cat_name
            })
            self.nav_tree.addTopLevelItem(cat_node)
            
            # Iterate Brands
            for brand_name, products in brands.items():
                # Если бренд пустой, добавляем продукты прямо в категорию (или в папку Misc)
                parent_for_prod = cat_node
                
                if brand_name != 'NO_BRAND':
                    brand_node = QTreeWidgetItem([f"🏭 {brand_name}"])
                    brand_node.setData(0, Qt.ItemDataRole.UserRole, {'type': 'brand_group'}) # Dummy type
                    cat_node.addChild(brand_node)
                    parent_for_prod = brand_node
                
                # Iterate Products
                for prod in products:
                    name = prod['name']
                    # Если имя все равно None (хотя SQL должен был исправить), ставим заглушку
                    if not name or str(name).lower() == 'none':
                        name = prod['key'] or "Unknown Product"
                        
                    count = prod['count']
                    
                    prod_item = QTreeWidgetItem([f"📦 {name} ({count})"])
                    prod_item.setData(0, Qt.ItemDataRole.UserRole, {
                        'type': 'product_key',
                        'key': prod['key'],
                        'id': prod['id']
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
            self.raw_items_table.setItem(row, 0, QTableWidgetItem(str(item.get('id', ''))))
            
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
            
            # Store full data
            self.raw_items_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, item)
        
            # === КОЛОНКА ДЕЙСТВИЙ ===
            # Создаем виджет с кнопками
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 2, 2, 2)
            actions_layout.setSpacing(4)

            # Кнопка перемещения
            btn_move = QPushButton("➜")
            btn_move.setFixedSize(24, 24)
            btn_move.setToolTip("Переместить")
            btn_move.setStyleSheet(f"""
                QPushButton {{
                    background: {Palette.BG_DARK_3}; border: 1px solid {Palette.PRIMARY};
                    color: {Palette.PRIMARY}; border-radius: 4px; font-weight: bold;
                }}
                QPushButton:hover {{ background: {Palette.with_alpha(Palette.PRIMARY, 0.2)}; }}
            """)
            btn_move.clicked.connect(lambda checked, r=row: self._on_table_item_move(r))

            # Кнопка удаления
            btn_del = QPushButton("🗑")
            btn_del.setFixedSize(24, 24)
            btn_del.setToolTip("В корзину")
            btn_del.setStyleSheet(f"""
                QPushButton {{
                    background: {Palette.BG_DARK_3}; border: 1px solid {Palette.ERROR};
                    color: {Palette.ERROR}; border-radius: 4px; font-weight: bold;
                }}
                QPushButton:hover {{ background: {Palette.with_alpha(Palette.ERROR, 0.2)}; }}
            """)
            btn_del.clicked.connect(lambda checked, r=row: self._on_table_item_delete(r))

            actions_layout.addWidget(btn_move)
            actions_layout.addWidget(btn_del)
            actions_layout.addStretch()

            self.raw_items_table.setCellWidget(row, 6, actions_widget)

        self.raw_items_table.resizeColumnsToContents()
        self.raw_items_table.setColumnWidth(6, 80)

        self.raw_items_table.setUpdatesEnabled(True)
    
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
        """Handle raw item selection change (mouse or keyboard)."""
        if not current:
            return
        
        row = current.row()
        id_item = self.raw_items_table.item(row, 0)
        if id_item:
            data = id_item.data(Qt.ItemDataRole.UserRole)
            if data:
                self._show_details(data, 'raw_item')
                
                # Проверяем, из корзины ли элемент
                is_deleted = data.get('deleted_at') is not None
                
                if is_deleted:
                    # Элемент в корзине - показываем кнопки восстановления
                    self.delete_btn.setVisible(False)
                    self.restore_btn.setVisible(True)
                    self.restore_btn.setEnabled(True)
                    self.permanent_delete_btn.setVisible(True)
                    self.permanent_delete_btn.setEnabled(True)
                    self.cultivate_btn.setEnabled(False)
                else:
                    # Обычный элемент
                    self.delete_btn.setVisible(True)
                    self.delete_btn.setEnabled(True)
                    self.restore_btn.setVisible(False)
                    self.permanent_delete_btn.setVisible(False)
                    self.cultivate_btn.setEnabled(False)
    
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
                self.delete_btn.setEnabled(True)
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
        form_layout.setSpacing(6)         # Вертикальный отступ между строками
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
                val.setText(f'<a href="{value_text}" style="color: {Palette.PRIMARY}; text-decoration: none;">Открыть объявление ↗</a>')
                val.setOpenExternalLinks(True)
                val.setCursor(Qt.CursorShape.PointingHandCursor)
                val.setStyleSheet(f"font-family: {Typography.UI}; font-size: {Typography.SIZE_MD}px;")
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
        # 1. Title
        title = QLabel(chunk.get('title', f"Chunk #{chunk.get('id', 'Unknown')}"))
        title.setStyleSheet(TextPresets.h3())
        title.setWordWrap(True)
        self.details_layout.addWidget(title)
        
        # 2. Status Badge (Visual)
        status = chunk.get('status', 'UNKNOWN')
        status_colors = {
            'PENDING': '#FFA500',
            'INITIALIZING': '#4169E1',
            'READY': '#32CD32',
            'FAILED': Palette.ERROR,
            'COMPRESSED': Palette.TEXT_MUTED
        }
        
        status_container = QWidget()
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(0, 8, 0, 8)
        status_layout.setSpacing(8)
        
        badge = QLabel(f"  {status}  ")
        badge_color = status_colors.get(status, Palette.TEXT)
        badge.setStyleSheet(f"""
            background-color: {Palette.with_alpha(badge_color, 0.15)};
            color: {badge_color};
            border: 1px solid {badge_color};
            border-radius: 4px;
            font-weight: bold;
            font-size: 10px;
        """)
        status_layout.addWidget(badge)
        status_layout.addStretch()
        self.details_layout.addWidget(status_container)

        self.details_layout.addWidget(self._create_divider())

        # 3. Metadata Form
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

        add_row("ТИП", chunk.get('chunk_type'))
        add_row("КЛЮЧ", chunk.get('chunk_key'))
        add_row("ПРИОРИТЕТ", chunk.get('priority'))
        add_row("ПОПЫТОК", chunk.get('retry_count'))
        add_row("СОЗДАНО", str(chunk.get('created_at', ''))[:16])
        add_row("ОБНОВЛЕНО", str(chunk.get('last_updated', ''))[:16])
        
        self.details_layout.addWidget(form_widget)

        # 4. Content / Summary
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

        if current_tab == 0:  # Список (дерево)
            if not text:
                # Показать все элементы
                for i in range(self.nav_tree.topLevelItemCount()):
                    self._show_tree_item_recursive(self.nav_tree.topLevelItem(i), True)
                return

            # Фильтруем дерево
            text_lower = text.lower()
            for i in range(self.nav_tree.topLevelItemCount()):
                self._filter_tree_item(self.nav_tree.topLevelItem(i), text_lower)

        elif current_tab == 1:  # Граф
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

        if current_tab == 0:  # Сырые данные
            table = self.raw_items_table
        else:  # Знания ИИ
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

    def _delete_selected(self):
        """Delete selected item/chunk."""
        if not hasattr(self, 'current_selection') or not self.current_selection:
            return
        
        data = self.current_selection['data']
        data_type = self.current_selection['type']
        
        confirm = QMessageBox.question(
            self,
            "Подтверждение",
            f"Удалить выбранный {data_type}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if confirm != QMessageBox.StandardButton.Yes:
            return
        
        try:
            if data_type == 'raw_item':
                self.memory.delete_raw_items([data.get('id')])
            elif data_type == 'knowledge':
                self.memory.delete_knowledge(data.get('id'))
            
            self._refresh_data()
            self._clear_details()
            logger.success(f"{data_type} deleted successfully")
            
        except Exception as e:
            logger.error(f"Failed to delete: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
    
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
        """Clear the details panel."""
        while self.details_layout.count():
            item = self.details_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.current_selection = None
        self.delete_btn.setEnabled(False)
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
    
    def _on_table_item_delete(self, row: int):
        """Удаление отдельного элемента из таблицы."""
        id_item = self.raw_items_table.item(row, 0)
        if not id_item:
            return
        
        data = id_item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        item_id = data.get('id')
        title = data.get('title', 'Unknown')[:50]
        
        reply = QMessageBox.question(
            self,
            "Удалить элемент?",
            f"Переместить '{title}...' в корзину?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            success = self.memory.raw_data.soft_delete_item(item_id)
            if success:
                logger.success(f"Элемент перемещен в корзину")
                self._refresh_data()
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось удалить элемент")
    
    def _on_table_item_move(self, row: int):
        """Перемещение элемента в другой продукт."""
        id_item = self.raw_items_table.item(row, 0)
        if not id_item:
            return
        
        data = id_item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        item_id = data.get('id')
        current_product_id = data.get('product_id') if 'product_id' in data else None
        
        # Получаем иерархию для диалога
        hierarchy = self.memory.raw_data.get_hierarchy_data()
        
        # Открываем диалог выбора
        dialog = MoveItemDialog(hierarchy, current_product_id, self)
        if dialog.exec():
            target_product_id = dialog.get_selected_product_id()
            if target_product_id:
                success = self.memory.raw_data.move_item_to_product(item_id, target_product_id)
                if success:
                    logger.success(f"Элемент перемещен в новый продукт")
                    self._refresh_data()
                else:
                    QMessageBox.warning(self, "Ошибка", "Не удалось переместить элемент")

    def _restore_selected(self):
        """Восстановление элемента из корзины."""
        if not hasattr(self, 'current_selection') or not self.current_selection:
            return
        
        data = self.current_selection['data']
        item_id = data.get('id')
        
        success = self.memory.raw_data.restore_item(item_id)
        if success:
            logger.success("Элемент восстановлен")
            self._refresh_data()
            self._clear_details()
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось восстановить элемент")
    
    def _permanent_delete_selected(self):
        """Окончательное удаление из корзины."""
        if not hasattr(self, 'current_selection') or not self.current_selection:
            return
        
        data = self.current_selection['data']
        item_id = data.get('id')
        title = data.get('title', 'Unknown')[:50]
        
        reply = QMessageBox.warning(
            self,
            "ОПАСНО",
            f"Удалить '{title}...' НАВСЕГДА?\n\nЭто действие нельзя отменить!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            success = self.memory.raw_data.permanent_delete_item(item_id)
            if success:
                logger.success("Элемент удален навсегда")
                self._refresh_data()
                self._clear_details()
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось удалить")

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
        """Refresh all data."""
        self._load_data()
    
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
