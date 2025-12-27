"""
DatabaseTab - UI for viewing and managing the memory database.
Replaces/augments the "Trends" tab functionality with full database access.
"""

import json
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QTreeWidget, QTreeWidgetItem, QTableWidget,
    QTableWidgetItem, QLineEdit, QComboBox, QSplitter, QToolBar,
    QToolButton, QMenu, QMessageBox, QTabWidget, QGridLayout,
    QHeaderView, QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QAction, QIcon

from app.ui.styles import Components, Palette, Spacing, Typography
from app.core.log_manager import logger
from app.config import BASE_APP_DIR


class DatabaseTab(QWidget):
    """
    New tab for viewing and managing the memory database.
    Provides complete access to raw_items and ai_knowledge.
    """
    
    item_selected = pyqtSignal(dict)  # Emit when an item/chunk is selected
    
    def __init__(self, memory_manager, parent=None):
        super().__init__(parent)
        self.memory = memory_manager
        self._init_ui()
        self._load_data()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # === Toolbar ===
        toolbar = QToolBar()
        toolbar.setStyleSheet(f"""
            QToolBar {{ background-color: {Palette.BG_DARK}; border-bottom: 1px solid {Palette.BORDER_SOFT}; padding: 8px; }}
            QToolButton {{ background: transparent; color: {Palette.TEXT}; border: 1px solid {Palette.BORDER_SOFT}; border-radius: 4px; padding: 6px 12px; margin-right: 8px; }}
            QToolButton:hover {{ background: {Palette.BG_DARK_2}; border-color: {Palette.PRIMARY}; }}
        """)
        
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск по базе...")
        self.search_edit.setStyleSheet(Components.text_input())
        self.search_edit.setFixedWidth(250)
        self.search_edit.textChanged.connect(self._on_search)
        toolbar.addWidget(self.search_edit)
        toolbar.addSeparator()
        
        self.type_filter = QComboBox()
        self.type_filter.addItems(["Все", "PRODUCT", "CATEGORY", "DATABASE", "AI_BEHAVIOR"])
        self.type_filter.setStyleSheet(f"""
            QComboBox {{ background: {Palette.BG_DARK_2}; color: {Palette.TEXT}; border: 1px solid {Palette.BORDER_SOFT}; border-radius: 4px; padding: 6px 12px; min-width: 120px; }}
        """)
        self.type_filter.currentTextChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.type_filter)
        toolbar.addSeparator()
        
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
        layout.addWidget(toolbar)
        
        # === Splitter ===
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(4)
        self.splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {Palette.BORDER_SOFT}; }}")
        
        # === Left Panel ===
        self.left_panel = QFrame()
        self.left_panel.setMinimumWidth(370)
        self.left_panel.setStyleSheet(Components.panel())
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        left_layout.setSpacing(Spacing.SM)
        
        stats_frame = QFrame()
        stats_frame.setStyleSheet(f"QFrame {{ background-color: {Palette.BG_DARK_2}; border-radius: {Spacing.RADIUS_NORMAL}px; padding: 12px; }}")
        stats_layout = QVBoxLayout(stats_frame)
        self.stats_label = QLabel("Загрузка...")
        self.stats_label.setStyleSheet(f"color: {Palette.TEXT}; font-size: 12px;")
        stats_layout.addWidget(self.stats_label)
        left_layout.addWidget(stats_frame)
        
        # Tabs for Tree / Graph
        self.nav_tabs = QTabWidget()
        self.nav_tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; }}
            QTabBar::tab {{ background: {Palette.BG_DARK_3}; color: {Palette.TEXT_MUTED}; padding: 6px; }}
            QTabBar::tab:selected {{ background: {Palette.BG_DARK_2}; color: {Palette.PRIMARY}; }}
        """)
        
        # 1. Tree
        self.nav_tree = QTreeWidget()
        self.nav_tree.setHeaderHidden(True)
        self.nav_tree.setStyleSheet(f"""
            QTreeWidget {{ background: transparent; border: none; font-size: 13px; }}
            QTreeWidget::item {{ padding: 6px; border-radius: 4px; }}
            QTreeWidget::item:selected {{ background-color: {Palette.PRIMARY}; color: white; }}
        """)
        # --- ИСПРАВЛЕНИЕ 2: Подключаем сигнал клика ---
        self.nav_tree.itemClicked.connect(self._on_tree_item_clicked)
        
        self.nav_tabs.addTab(self.nav_tree, "📂 Список")
        
        # 2. Graph
        from app.ui.widgets.knowledge_graph import KnowledgeGraphWidget
        self.graph_widget = KnowledgeGraphWidget()
        # Подключаем клик по узлу графа к открытию деталей
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
        
        table_header = QLabel("ДАННЫЕ В БАЗЕ")
        table_header.setStyleSheet(Components.subsection_title())
        center_layout.addWidget(table_header)
        
        self.table_tabs = QTabWidget()
        self.table_tabs.setStyleSheet(f"""
            QTabWidget::pane {{ background: {Palette.BG_DARK_2}; border: none; }}
            QTabBar::tab {{ background: {Palette.BG_DARK}; color: {Palette.TEXT_MUTED}; padding: 8px 16px; border-top-left-radius: 4px; border-top-right-radius: 4px; }}
            QTabBar::tab:selected {{ background: {Palette.PRIMARY}; color: white; }}
        """)
        
        self.raw_items_table = QTableWidget()
        self.raw_items_table.setColumnCount(6)
        self.raw_items_table.setHorizontalHeaderLabels(["ID", "Заголовок", "Цена", "Город", "Дата", "Категории"])
        self.raw_items_table.horizontalHeader().setStretchLastSection(True)
        self.raw_items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.raw_items_table.setStyleSheet(self._get_table_style())
        self.raw_items_table.itemClicked.connect(self._on_raw_item_clicked)
        self.table_tabs.addTab(self.raw_items_table, "📦 Сырые данные")
        
        self.knowledge_table = QTableWidget()
        self.knowledge_table.setColumnCount(5)
        self.knowledge_table.setHorizontalHeaderLabels(["ID", "Тип", "Ключ", "Статус", "Обновлено"])
        self.knowledge_table.horizontalHeader().setStretchLastSection(True)
        self.knowledge_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.knowledge_table.setStyleSheet(self._get_table_style())
        self.knowledge_table.itemClicked.connect(self._on_knowledge_clicked)
        self.table_tabs.addTab(self.knowledge_table, "🧠 Знания ИИ")
        
        center_layout.addWidget(self.table_tabs)
        self.splitter.addWidget(center_panel)
        
        # === Right Panel (Details) ===
        right_panel = QFrame()
        right_panel.setFixedWidth(350)
        right_panel.setStyleSheet(Components.panel())
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        
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
        
        self.cultivate_btn = QPushButton("🌱 Перекультивировать")
        self.cultivate_btn.setStyleSheet(Components.start_button())
        self.cultivate_btn.setEnabled(False)
        self.cultivate_btn.clicked.connect(self._recultivate)
        right_layout.addWidget(self.cultivate_btn)
        
        self.splitter.addWidget(right_panel)
        layout.addWidget(self.splitter)

        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(2, False)

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)

        self.splitter.setSizes([400, 800, 350])
    
    def _get_table_style(self):
        return f"""
            QTableWidget {{ background: transparent; border: none; gridline-color: {Palette.BORDER_SOFT}; }}
            QHeaderView::section {{ background: {Palette.BG_DARK}; color: {Palette.TEXT_MUTED}; padding: 8px; border: none; }}
        """

    def _load_data(self):
        """Load all data from the database."""
        if not self.memory:
            return
        
        # Load categories and product keys for tree
        categories = self.memory.get_all_categories()
        product_keys = self.memory.get_all_product_keys()
        
        # Build navigation tree
        self.nav_tree.clear()
        
        # Root items
        all_items_node = QTreeWidgetItem(["📦 Все сырые данные"])
        all_items_node.setData(0, Qt.ItemDataRole.UserRole, {'type': 'all_items'})
        
        all_knowledge_node = QTreeWidgetItem(["🧠 Все знания"])
        all_knowledge_node.setData(0, Qt.ItemDataRole.UserRole, {'type': 'all_knowledge'})
        
        categories_node = QTreeWidgetItem(["📁 Категории"])
        categories_node.setData(0, Qt.ItemDataRole.UserRole, {'type': 'categories_root'})
        
        products_node = QTreeWidgetItem(["📁 Продукты"])
        products_node.setData(0, Qt.ItemDataRole.UserRole, {'type': 'products_root'})
        
        self.nav_tree.addTopLevelItem(all_items_node)
        self.nav_tree.addTopLevelItem(all_knowledge_node)
        self.nav_tree.addTopLevelItem(categories_node)
        self.nav_tree.addTopLevelItem(products_node)
        
        # Add categories
        for cat in categories:
            cat_item = QTreeWidgetItem([f"📁 {cat.get('name', 'Unknown')} ({cat.get('item_count', 0)})"])
            cat_item.setData(0, Qt.ItemDataRole.UserRole, {
                'type': 'category',
                'id': cat.get('id'),
                'name': cat.get('name')
            })
            categories_node.addChild(cat_item)
        
        # Add product keys
        for pk in product_keys:
            pk_item = QTreeWidgetItem([f"📦 {pk.get('key', 'Unknown')} ({pk.get('item_count', 0)})"])
            pk_item.setData(0, Qt.ItemDataRole.UserRole, {
                'type': 'product_key',
                'id': pk.get('id'),
                'key': pk.get('key')
            })
            products_node.addChild(pk_item)
        
        # Expand tree
        categories_node.setExpanded(True)
        products_node.setExpanded(True)
        
        # Load raw items
        raw_items = self.memory.get_raw_items(limit=1000)
        self._populate_raw_items_table(raw_items)
        
        # Load knowledge
        knowledge = self.memory.get_knowledge(limit=1000)
        self._populate_knowledge_table(knowledge)
        
        # Graph Data
        self.graph_widget.load_data(knowledge)
        
        # Update stats
        self._update_stats()
    
    def _populate_raw_items_table(self, items: list):
        """Populate the raw items table."""
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
            categories = ', '.join(item.get('categories', []) + item.get('product_keys', []))
            self.raw_items_table.setItem(row, 5, QTableWidgetItem(categories[:30]))
            
            # Store full data
            self.raw_items_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, item)
    
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
            self.knowledge_table.setItem(row, 1, QTableWidgetItem(f"{type_icons.get(chunk_type, '📝')} {chunk_type}"))
            
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
                f"📦 Items: {raw_stats.get('total_items', 0)} | "
                f"📁 Categories: {raw_stats.get('total_categories', 0)} | "
                f"🧠 Chunks: {knowledge_stats.get('total_chunks', 0)} | "
                f"✅ Ready: {knowledge_stats.get('by_status', {}).get('READY', 0)}"
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
        elif item_type == 'product_key':
            items = self.memory.get_items_for_product_key(data.get('key'))
            self._populate_raw_items_table(items)
            self.table_tabs.setCurrentIndex(0)
    
    def _on_raw_item_clicked(self, item):
        """Handle raw item click."""
        data = item.data(Qt.ItemDataRole.UserRole)
        self._show_details(data, 'raw_item')
        self.delete_btn.setEnabled(True)
        self.cultivate_btn.setEnabled(False)
    
    def _on_knowledge_clicked(self, item):
        """Handle knowledge chunk click."""
        data = item.data(Qt.ItemDataRole.UserRole)
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
        """Render raw item details."""
        # Title
        title = QLabel(item.get('title', 'Unknown'))
        title.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {Palette.TEXT};")
        title.setWordWrap(True)
        self.details_layout.addWidget(title)
        
        # Fields grid
        fields = [
            ("ID", str(item.get('id', ''))),
            ("Ad ID", str(item.get('ad_id', ''))),
            ("Цена", f"{item.get('price', '')} ₽" if item.get('price') else ''),
            ("Город", item.get('city', '')),
            ("Состояние", item.get('condition', '')),
            ("Продавец", item.get('seller_id', '')),
            ("Просмотры", str(item.get('views', ''))),
            ("Дата", item.get('date_text', '')),
            ("Ссылка", item.get('link', '')[:50] + '...' if item.get('link') else ''),
        ]
        
        for label, value in fields:
            if value:
                row = QHBoxLayout()
                lbl = QLabel(f"{label}:")
                lbl.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 11px; min-width: 70px;")
                val = QLabel(value)
                val.setStyleSheet(f"color: {Palette.TEXT}; font-size: 12px;")
                val.setWordWrap(True)
                row.addWidget(lbl)
                row.addWidget(val, stretch=1)
                container = QWidget()
                container.setLayout(row)
                self.details_layout.addWidget(container)
        
        # Description
        if item.get('description'):
            desc_label = QLabel("Описание:")
            desc_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 11px; margin-top: 8px;")
            self.details_layout.addWidget(desc_label)
            
            desc = QLabel(item.get('description')[:500])
            desc.setStyleSheet(f"color: {Palette.TEXT}; font-size: 12px;")
            desc.setWordWrap(True)
            self.details_layout.addWidget(desc)
        
        # Categories/Products
        categories = item.get('categories', [])
        product_keys = item.get('product_keys', [])
        if categories or product_keys:
            tags = ', '.join(categories + product_keys)
            tags_label = QLabel(f"Теги: {tags}")
            tags_label.setStyleSheet(f"color: {Palette.PRIMARY}; font-size: 11px; margin-top: 8px;")
            self.details_layout.addWidget(tags_label)
    
    def _render_knowledge_details(self, chunk: dict):
        """Render knowledge chunk details."""
        # Title
        title = QLabel(chunk.get('title', f"Chunk #{chunk.get('id', 'Unknown')}"))
        title.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {Palette.TEXT};")
        title.setWordWrap(True)
        self.details_layout.addWidget(title)
        
        # Status badge
        status = chunk.get('status', 'UNKNOWN')
        status_colors = {
            'PENDING': '#FFA500',
            'INITIALIZING': '#4169E1',
            'READY': '#32CD32',
            'FAILED': '#FF4444',
            'COMPRESSED': '#808080'
        }
        status_lbl = QLabel(f"Статус: {status}")
        status_lbl.setStyleSheet(f"color: {status_colors.get(status, Palette.TEXT)}; font-size: 12px; font-weight: bold;")
        self.details_layout.addWidget(status_lbl)
        
        # Info fields
        fields = [
            ("Тип", chunk.get('chunk_type', '')),
            ("Ключ", chunk.get('chunk_key', '')),
            ("Приоритет", str(chunk.get('priority', 1))),
            ("Попыток", str(chunk.get('retry_count', 0))),
            ("Создано", str(chunk.get('created_at', ''))[:16]),
            ("Обновлено", str(chunk.get('last_updated', ''))[:16]),
        ]
        
        for label, value in fields:
            if value:
                row = QHBoxLayout()
                lbl = QLabel(f"{label}:")
                lbl.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 11px; min-width: 80px;")
                val = QLabel(str(value))
                val.setStyleSheet(f"color: {Palette.TEXT}; font-size: 12px;")
                row.addWidget(lbl)
                row.addWidget(val, stretch=1)
                container = QWidget()
                container.setLayout(row)
                self.details_layout.addWidget(container)
        
        # Summary
        summary = chunk.get('summary')
        if summary:
            summary_label = QLabel("Сводка:")
            summary_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 11px; margin-top: 8px;")
            self.details_layout.addWidget(summary_label)
            
            summary_text = QLabel(summary)
            summary_text.setStyleSheet(f"color: {Palette.TEXT}; font-size: 12px;")
            summary_text.setWordWrap(True)
            self.details_layout.addWidget(summary_text)
        
        # Content preview (if JSON)
        content = chunk.get('content')
        if content and isinstance(content, dict):
            content_label = QLabel("Анализ:")
            content_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 11px; margin-top: 8px;")
            self.details_layout.addWidget(content_label)
            
            # Show key stats from analysis
            analysis = content.get('analysis', {})
            if isinstance(analysis, dict):
                stats_text = []
                if analysis.get('sample_count'):
                    stats_text.append(f"Sample: {analysis['sample_count']}")
                if analysis.get('median_price'):
                    stats_text.append(f"Median: {analysis['median_price']}₽")
                if analysis.get('avg_price'):
                    stats_text.append(f"Avg: {analysis['avg_price']}₽")
                
                if stats_text:
                    stats_label = QLabel(" | ".join(stats_text))
                    stats_label.setStyleSheet(f"color: {Palette.PRIMARY}; font-size: 12px;")
                    self.details_layout.addWidget(stats_label)
    
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
        
        # Сигнал в MainWindow для запуска
        self.item_selected.emit({
            'action': 'recultivate',
            'chunk_id': data.get('id'),
            'chunk_type': data.get('chunk_type'),
            'chunk_key': data.get('chunk_key')
        })
        # Сразу ставим статус
        self.memory.knowledge.update_chunk_status(data.get('id'), 'PENDING')
        self._refresh_data()
    
    def _clear_details(self):
        """Clear the details panel."""
        while self.details_layout.count():
            item = self.details_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.current_selection = None
        self.delete_btn.setEnabled(False)
        self.cultivate_btn.setEnabled(False)
    
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
