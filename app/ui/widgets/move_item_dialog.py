from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QLineEdit, QTreeWidgetItemIterator
)
from PyQt6.QtCore import Qt
from app.ui.styles import Components, Palette, Spacing, Typography
from typing import Dict, Optional


class MoveItemDialog(QDialog):
    """
    Диалог для перемещения элемента между категориями/продуктами.
    """
    
    def __init__(self, hierarchy: Dict, current_product_id: int = None, parent=None):
        super().__init__(parent)
        self.hierarchy = hierarchy
        self.current_product_id = current_product_id
        self.selected_product_id = None
        
        self.setWindowTitle("Переместить элемент")
        self.setModal(True)
        self.setStyleSheet(Components.dialog())
        self.resize(450, 600)
        
        self._init_ui()
        self._load_hierarchy()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.MD)
        
        # Header
        header = QLabel("ВЫБЕРИТЕ НОВОЕ РАСПОЛОЖЕНИЕ")
        header.setStyleSheet(Components.section_title())
        layout.addWidget(header)
        
        # Поиск
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 Поиск категории/продукта...")
        self.search_edit.setStyleSheet(Components.text_input())
        self.search_edit.textChanged.connect(self._on_search)
        layout.addWidget(self.search_edit)
        
        # Дерево
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background: {Palette.BG_DARK_2};
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: {Spacing.RADIUS_NORMAL}px;
                color: {Palette.TEXT};
                font-size: 13px;
            }}
            QTreeWidget::item {{
                padding: 6px;
                border-radius: 4px;
            }}
            QTreeWidget::item:hover {{
                background-color: {Palette.BG_DARK_3};
            }}
            QTreeWidget::item:selected {{
                background-color: {Palette.PRIMARY};
                color: white;
            }}
        """)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.tree)
        
        # Info label
        self.info_label = QLabel("Выберите продукт из списка")
        self.info_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: {Typography.SIZE_SM}px; font-style: italic;")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        btn_cancel = QPushButton("Отмена")
        btn_cancel.setStyleSheet(Components.stop_button())
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        
        self.btn_ok = QPushButton("Переместить")
        self.btn_ok.setStyleSheet(Components.start_button())
        self.btn_ok.setEnabled(False)
        self.btn_ok.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_ok)
        
        layout.addLayout(btn_layout)
    
    def _load_hierarchy(self):
        self.tree.clear()
        
        for cat_name, brands in sorted(self.hierarchy.items()):
            cat_item = QTreeWidgetItem([f"📁 {cat_name}"])
            cat_item.setData(0, Qt.ItemDataRole.UserRole, {'type': 'category', 'name': cat_name})
            cat_item.setExpanded(True)
            self.tree.addTopLevelItem(cat_item)
            
            for brand_name, products in sorted(brands.items()):
                parent_item = cat_item
                
                # Если есть бренд, создаем узел бренда
                if brand_name != 'NO_BRAND':
                    brand_item = QTreeWidgetItem([f"🏭 {brand_name}"])
                    brand_item.setData(0, Qt.ItemDataRole.UserRole, {'type': 'brand'})
                    cat_item.addChild(brand_item)
                    parent_item = brand_item
                
                # Добавляем продукты
                for prod in products:
                    prod_name = prod['name'] or prod['key']
                    count = prod['count']
                    prod_item = QTreeWidgetItem([f"📦 {prod_name} ({count})"])
                    prod_item.setData(0, Qt.ItemDataRole.UserRole, {
                        'type': 'product',
                        'id': prod['id'],
                        'key': prod['key'],
                        'name': prod_name
                    })
                    
                    # Отключаем текущий продукт
                    if self.current_product_id and prod['id'] == self.current_product_id:
                        prod_item.setDisabled(True)
                        prod_item.setText(0, f"📦 {prod_name} ({count}) [ТЕКУЩЕЕ]")
                    
                    parent_item.addChild(prod_item)
    
    def _on_search(self, text: str):
        """
        Фильтрация дерева по поисковому запросу.
        """
        if not text:
            # Показать все
            iterator = QTreeWidgetItemIterator(self.tree)
            while iterator.value():
                iterator.value().setHidden(False)
                iterator += 1
            return
        
        text_lower = text.lower()
        
        def match_and_show_parents(item):
            """Рекурсивная проверка и показ родителей."""
            item_text = item.text(0).lower()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            
            # Проверяем совпадение
            match = text_lower in item_text
            
            # Проверяем детей
            child_match = False
            for i in range(item.childCount()):
                if match_and_show_parents(item.child(i)):
                    child_match = True
            
            # Показываем если есть совпадение или совпадают дети
            visible = match or child_match
            item.setHidden(not visible)
            
            # Разворачиваем если есть совпадение в детях
            if child_match:
                item.setExpanded(True)
            
            return visible
        
        # Применяем фильтр ко всем top-level items
        for i in range(self.tree.topLevelItemCount()):
            match_and_show_parents(self.tree.topLevelItem(i))
    
    def _on_item_clicked(self, item, column):
        """
        Обработка клика по элементу.
        """
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        if data.get('type') == 'product' and not item.isDisabled():
            self.selected_product_id = data['id']
            product_name = data['name']
            self.info_label.setText(f"✓ Выбран продукт: {product_name}")
            self.info_label.setStyleSheet(f"color: {Palette.SUCCESS}; font-size: {Typography.SIZE_SM}px; font-weight: bold;")
            self.btn_ok.setEnabled(True)
        else:
            self.selected_product_id = None
            self.info_label.setText("Выберите продукт из списка")
            self.info_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: {Typography.SIZE_SM}px; font-style: italic;")
            self.btn_ok.setEnabled(False)
    
    def _on_item_double_clicked(self, item, column):
        """
        Двойной клик для быстрого перемещения.
        """
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get('type') == 'product' and not item.isDisabled():
            self.selected_product_id = data['id']
            self.accept()
    
    def get_selected_product_id(self) -> Optional[int]:
        """
        Возвращает ID выбранного продукта.
        """
        return self.selected_product_id