from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, 
    QScrollArea, QLineEdit, QLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QRect, QPoint, QTimer
from app.ui.styles import Palette, Spacing, Typography, Components

# Automatic layout for positioning and scaling tags
class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.item_list = []
    
    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)
    
    def addItem(self, item):
        self.item_list.append(item)
    
    def count(self):
        return len(self.item_list)
    
    def itemAt(self, index):
        if 0 <= index < len(self.item_list):
            return self.item_list[index]
        return None
    
    def takeAt(self, index):
        if 0 <= index < len(self.item_list):
            return self.item_list.pop(index)
        return None
    
    def expandingDirections(self):
        return Qt.Orientation(0)
    
    def hasHeightForWidth(self):
        return True
    
    def heightForWidth(self, width):
        height = self.doLayout(QRect(0, 0, width, 0), True)
        return height
    
    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.doLayout(rect, False)
    
    def sizeHint(self):
        return self.minimumSize()
    
    def minimumSize(self):
        size = QSize()
        for item in self.item_list:
            size = size.expandedTo(item.minimumSize())
        margin, _, _, _ = self.getContentsMargins()
        size += QSize(2 * margin, 2 * margin)
        return size
    
    def doLayout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self.spacing()
        for item in self.item_list:
            style = item.widget().style()
            layout_spacing_x = style.layoutSpacing(
                QSizePolicy.ControlType.PushButton, 
                QSizePolicy.ControlType.PushButton, 
                Qt.Orientation.Horizontal
            )
            layout_spacing_y = style.layoutSpacing(
                QSizePolicy.ControlType.PushButton, 
                QSizePolicy.ControlType.PushButton, 
                Qt.Orientation.Vertical
            )
            space_x = spacing + layout_spacing_x
            space_y = spacing + layout_spacing_y
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = next_x
            line_height = max(line_height, item.sizeHint().height())
        return y + line_height - rect.y()

class TagWidget(QFrame):
    removed = pyqtSignal(str)
    
    def __init__(self, text, parent=None, color=Palette.PRIMARY):
        super().__init__(parent)
        self.text = text
        self.setFrameShape(QFrame.Shape.NoFrame)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, 2, Spacing.SM, 2)
        layout.setSpacing(Spacing.XS)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.label = QLabel(text)
        self.label.setStyleSheet(f"color: {Palette.TEXT}; font-weight: {Typography.WEIGHT_MEDIUM}; background: transparent;")
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        self.delete_btn = QPushButton("×")
        self.delete_btn.setFixedSize(14, 14)
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                border-radius: 7px;
                background-color: {Palette.with_alpha(Palette.TEXT, 0.2)};
                color: {Palette.TEXT};
                font-weight: bold;
                padding: 0;
                margin: 0;
            }}
            QPushButton:hover {{ background-color: {Palette.with_alpha(Palette.TEXT, 0.4)}; }}
        """)
        self.delete_btn.clicked.connect(self._on_delete)
        
        layout.addWidget(self.label)
        layout.addWidget(self.delete_btn)
        
        # Полупрозрачный фон с акцентной рамкой
        self.setStyleSheet(f"""
            TagWidget {{
                background-color: {Palette.with_alpha(color, 0.15)};
                border: 1px solid {color};
                border-radius: {Spacing.RADIUS_NORMAL}px;
            }}
        """)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        
    def _on_delete(self):
        self.removed.emit(self.text)
        
    def sizeHint(self):
        return QSize(self.label.sizeHint().width() + 24, 26)

class TagsInput(QWidget):
    tags_changed = pyqtSignal(list)
    
    def __init__(self, title="", parent=None, tag_color=Palette.PRIMARY, validator=None):
        super().__init__(parent)
        self.tag_color = tag_color
        self.clear_btn = None
        self.validator = validator
        
        self.setStyleSheet(f"""
            TagsInput {{
                background-color: {Palette.BG_LIGHT};
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: {Spacing.RADIUS_NORMAL}px;
            }}
        """)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Header
        self.header_container = QWidget()
        self.header_container.setStyleSheet(f"""
            background-color: {Palette.BG_DARK_3};
            border-bottom: 1px solid {Palette.BORDER_SOFT};
            border-top-left-radius: {Spacing.RADIUS_NORMAL}px;
            border-top-right-radius: {Spacing.RADIUS_NORMAL}px;
        """)
        self.header_layout = QHBoxLayout(self.header_container)
        self.header_layout.setContentsMargins(Spacing.MD, Spacing.XS, Spacing.SM, Spacing.XS)
        self.header_layout.setSpacing(Spacing.SM)
        
        if title:
            self.title_label = QLabel(title)
            self.title_label.setStyleSheet(
                Typography.style(
                    family=Typography.UI,
                    size=Typography.SIZE_SM,
                    weight=Typography.WEIGHT_BOLD,
                    color=Palette.TEXT_MUTED,
                    letter_spacing=Typography.SPACING_WIDE
                )
            )
            self.header_layout.addWidget(self.title_label)
        
        self.header_layout.addStretch()
        
        # Scroll Area for Tags
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background: transparent;")
        
        self.tags_container = QWidget()
        self.tags_container.setStyleSheet("background: transparent;")
        
        self.padder_layout = QVBoxLayout(self.tags_container)
        self.padder_layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        self.padder_layout.setSpacing(0)
        
        self.inner_tags_widget = QWidget()
        self.inner_tags_widget.setStyleSheet("background: transparent;")
        self.padder_layout.addWidget(self.inner_tags_widget)
        
        self.tags_layout = FlowLayout(self.inner_tags_widget, margin=0, spacing=Spacing.SM)
        self.tags_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll_area.setWidget(self.tags_container)
        
        # Input Field
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Введите и нажмите Enter...")
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                border: none;
                border-top: 1px solid {Palette.BORDER_SOFT};
                background: {Palette.BG_LIGHT};
                padding: {Spacing.SM}px {Spacing.MD}px;
                color: {Palette.TEXT};
                font-family: {Typography.UI};
                font-size: {Typography.SIZE_MD}px;
                border-bottom-left-radius: {Spacing.RADIUS_NORMAL}px;
                border-bottom-right-radius: {Spacing.RADIUS_NORMAL}px;
            }}
            QLineEdit:focus {{
                background: {Palette.BG_DARK_3};
                border-top: 1px solid {self.tag_color};
            }}
        """)
        self.input_field.returnPressed.connect(self._add_tag_from_input)
        
        self.main_layout.addWidget(self.header_container)
        self.main_layout.addWidget(self.scroll_area)
        self.main_layout.addWidget(self.input_field)
        
        self.tags = []

    def set_clear_button(self, btn: QPushButton):
        self.clear_btn = btn
        self.header_layout.addWidget(btn)

    def _add_tag_from_input(self):
        text = self.input_field.text().strip()
        if not text: return
        if self.validator and not self.validator(text): return
        if text not in self.tags: self.add_tag(text)
        self.input_field.clear()
        
    def add_tag(self, text):
        if not text or text in self.tags: return
        tag_widget = TagWidget(text, color=self.tag_color)
        tag_widget.removed.connect(self._remove_tag)
        self.tags_layout.addWidget(tag_widget)
        self.tags.append(text)
        self.tags_changed.emit(self.tags)
        self._update_geometry()
        QTimer.singleShot(10, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        if self.scroll_area.verticalScrollBar():
            self.scroll_area.verticalScrollBar().setValue(
                self.scroll_area.verticalScrollBar().maximum()
            )
        
    def _remove_tag(self, text):
        i = 0
        while i < self.tags_layout.count():
            item = self.tags_layout.itemAt(i)
            w = item.widget()
            if isinstance(w, TagWidget) and w.text == text:
                self.tags_layout.takeAt(i)
                w.setParent(None)
                w.deleteLater()
                continue
            i += 1
        if text in self.tags:
            self.tags.remove(text)
            self.tags_changed.emit(self.tags)
        self._update_geometry()
            
    def _update_geometry(self):
        self.inner_tags_widget.adjustSize()
        self.tags_container.adjustSize()
            
    def get_tags(self): return self.tags.copy()
    
    def clear_tags(self):
        while self.tags_layout.count():
            item = self.tags_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.tags = []
        self.tags_changed.emit(self.tags)
        self._update_geometry()

    def set_tags(self, tags):
        self.clear_tags()
        if not tags: return
        for t in tags:
            if t and str(t).strip(): self.add_tag(str(t).strip())