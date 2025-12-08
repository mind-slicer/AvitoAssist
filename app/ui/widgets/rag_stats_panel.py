from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy, QGridLayout
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from app.ui.styles import Palette, Typography, Components, Spacing

class RAGStatsPanel(QWidget):
    navigate_to_rag = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RAGStatsPanel")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        
        main = QVBoxLayout(self)
        main.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        main.setSpacing(Spacing.SM)
        
        # Заголовок
        title_rag = QLabel("RAG ПАМЯТЬ")
        title_rag.setCursor(Qt.CursorShape.PointingHandCursor)
        title_rag.mousePressEvent = lambda event: self.navigate_to_rag.emit()
        title_rag.setStyleSheet(Components.section_title())
        main.addWidget(title_rag)
        
        # Grid layout для компактности
        grid = QGridLayout()
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 1)
        grid.setSpacing(Spacing.SM)
        grid.setContentsMargins(0, 0, 0, 0)
        
        # Строка 0: Товары
        icon_items = QLabel("📦")
        icon_items.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_items = QLabel("Товары")
        name_items.setStyleSheet(Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_MD,
            weight=Typography.WEIGHT_SEMIBOLD,
            color=Palette.TEXT_MUTED
        ))
        self.lbl_items = QLabel("0")
        self.lbl_items.setStyleSheet(Typography.style(
            family=Typography.MONO,
            size=Typography.SIZE_MD,
            color=Palette.TEXT
        ))
        grid.addWidget(icon_items, 0, 0)
        grid.addWidget(name_items, 0, 1)
        grid.addWidget(self.lbl_items, 0, 2)
        
        # Строка 1: Категории
        icon_cats = QLabel("📊")
        icon_cats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_cats = QLabel("Категории")
        name_cats.setStyleSheet(Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_MD,
            weight=Typography.WEIGHT_SEMIBOLD,
            color=Palette.TEXT_MUTED
        ))
        self.lbl_categories = QLabel("0")
        self.lbl_categories.setStyleSheet(Typography.style(
            family=Typography.MONO,
            size=Typography.SIZE_MD,
            color=Palette.TEXT
        ))
        grid.addWidget(icon_cats, 1, 0)
        grid.addWidget(name_cats, 1, 1)
        grid.addWidget(self.lbl_categories, 1, 2)
        
        # Строка 2: Статус
        icon_status = QLabel("🔄")
        icon_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_status = QLabel("Статус")
        name_status.setStyleSheet(Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_MD,
            weight=Typography.WEIGHT_SEMIBOLD,
            color=Palette.TEXT_MUTED
        ))
        self.lbl_status = QLabel("Пусто")
        self.lbl_status.setStyleSheet(Typography.style(
            family=Typography.MONO,
            size=Typography.SIZE_MD,
            color=Palette.TEXT_MUTED
        ))
        grid.addWidget(icon_status, 2, 0)
        grid.addWidget(name_status, 2, 1)
        grid.addWidget(self.lbl_status, 2, 2)
        
        # Строка 3: Обновлено
        icon_update = QLabel("⏱️")
        icon_update.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_update = QLabel("Обновлено")
        name_update.setStyleSheet(Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_MD,
            weight=Typography.WEIGHT_SEMIBOLD,
            color=Palette.TEXT_MUTED
        ))
        self.lbl_updated = QLabel("—")
        self.lbl_updated.setStyleSheet(Typography.style(
            family=Typography.MONO,
            size=Typography.SIZE_SM,
            color=Palette.TEXT_MUTED
        ))
        grid.addWidget(icon_update, 3, 0)
        grid.addWidget(name_update, 3, 1)
        grid.addWidget(self.lbl_updated, 3, 2)
        
        main.addLayout(grid)
        self.setStyleSheet(Components.panel())
    
    def update_stats(self, stats: dict):
        """
        Обновить статистику RAG
        Args:
            stats: {total_items, total_categories, last_rebuild, status}
        """
        total_items = stats.get('total_items', 0)
        total_categories = stats.get('total_categories', 0)
        last_rebuild = stats.get('last_rebuild', 'Never')
        status = stats.get('status', 'empty')
        
        # Товары
        self.lbl_items.setText(str(total_items))
        
        # Категории
        self.lbl_categories.setText(str(total_categories))
        
        # Статус
        status_map = {
            'ok': ('✅ Актуально', Palette.SUCCESS),
            'outdated': ('⚠️ Устарело', Palette.WARNING),
            'empty': ('❌ Пусто', Palette.TEXT_MUTED)
        }
        status_text, status_color = status_map.get(status, ('—', Palette.TEXT_MUTED))
        self.lbl_status.setText(status_text)
        self.lbl_status.setStyleSheet(Typography.style(
            family=Typography.MONO,
            size=Typography.SIZE_MD,
            color=status_color
        ))
        
        # Последнее обновление
        if last_rebuild and last_rebuild != 'Never':
            # Форматируем дату
            try:
                from datetime import datetime
                dt = datetime.strptime(last_rebuild, "%Y-%m-%d %H:%M:%S")
                formatted = dt.strftime("%d.%m %H:%M")
            except:
                formatted = last_rebuild[:16]
            self.lbl_updated.setText(formatted)
        else:
            self.lbl_updated.setText("—")