from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSpinBox, QPushButton, QSizePolicy, QCheckBox, QComboBox
from PyQt6.QtCore import Qt, QPropertyAnimation, QPoint, pyqtProperty
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen
from app.ui.styles import Palette, Spacing, Components, Typography

class PriceSpinBox(QSpinBox):
    def __init__(self, default_value: int = 0, placeholder: str = "∞"):
        super().__init__()
        self.setRange(0, 9_999_999)
        self.setSingleStep(100)
        self.setValue(default_value)
        self.setSpecialValueText(placeholder)
        self.default_value = default_value
        self.setStyleSheet(Components.text_input())
    
    def reset_to_default(self):
        self.setValue(self.default_value)

class NoScrollComboBox(QComboBox):
    """ComboBox без прокрутки колесом мыши"""
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def wheelEvent(self, event):
        # Игнорируем прокрутку мыши
        event.ignore()
    
    def showPopup(self):
        """Открывает выпадающее меню всегда вниз"""
        super().showPopup()
        # Фиксируем позицию popup
        popup = self.view().parent()
        if popup:
            # Вычисляем позицию чтобы открыть вниз
            pos = self.mapToGlobal(self.rect().bottomLeft())
            popup.move(pos)

class AnimatedToggle(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(44, 24)
        
        # Цвета для состояний
        self._bg_off = QColor(Palette.BG_DARK)
        self._border_off = QColor(Palette.BORDER_SOFT)
        self._circle_off = QColor(Palette.TEXT_MUTED)
        
        self._bg_on = QColor(Palette.PRIMARY)
        self._border_on = QColor(Palette.PRIMARY)
        self._circle_on = QColor(Palette.TEXT_ON_PRIMARY)
        
        self._circle_position = 3.0
        
        self.animation = QPropertyAnimation(self, b"circle_position", self)
        self.animation.setDuration(150)
        self.stateChanged.connect(self.start_animation)
    
    @pyqtProperty(float)
    def circle_position(self):
        return self._circle_position
    
    @circle_position.setter
    def circle_position(self, pos):
        self._circle_position = pos
        self.update()
    
    def start_animation(self, state):
        self.animation.stop()
        circle_size = self.height() - 6.0 
        end_pos = self.width() - circle_size - 3.0 if state else 3.0
        self.animation.setEndValue(end_pos)
        self.animation.start()
    
    def hitButton(self, pos: QPoint):
        return self.rect().contains(pos)
    
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        track_h = rect.height()
        track_w = rect.width()
        radius = track_h / 2
        
        if self.isChecked():
            bg_brush = QBrush(self._bg_on)
            border_pen = QPen(self._border_on, 1)
            circle_brush = QBrush(self._circle_on)
        else:
            bg_brush = QBrush(self._bg_off)
            border_pen = QPen(self._border_off, 1)
            circle_brush = QBrush(self._circle_off)
        
        if not self.isEnabled():
            # Затемнение если выключен
            bg_brush = QBrush(QColor(Palette.BG_DARK_2))
            border_pen = QPen(QColor(Palette.DIVIDER), 1)
            circle_brush = QBrush(QColor(Palette.TEXT_MUTED))

        # Рисуем трек (фон)
        p.setBrush(bg_brush)
        p.setPen(border_pen)
        p.drawRoundedRect(0, 0, track_w, track_h, radius, radius)
        
        # Рисуем кружок
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(circle_brush)
        
        circle_size = track_h - 6.0 # Отступ по 3px сверху и снизу
        circle_y = 3.0
        
        p.drawEllipse(
            int(self._circle_position), 
            int(circle_y), 
            int(circle_size), 
            int(circle_size)
        )

class ParamInput(QWidget):
    def __init__(self, label_text, spinbox: QSpinBox, width: int | None = None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.XS)
        
        self.label = QLabel(label_text)
        self.label.setStyleSheet(
            Typography.style(
                family=Typography.UI,
                size=Typography.SIZE_MD,
                color=Palette.TEXT_MUTED,
            )
        )
        layout.addWidget(self.label)
        
        self.container = QFrame()
        self.container.setStyleSheet(Components.card())
        
        if width:
            self.container.setFixedWidth(width)
            
        hlayout = QHBoxLayout(self.container)
        hlayout.setContentsMargins(Spacing.XS, Spacing.XS, Spacing.XS, Spacing.XS)
        hlayout.setSpacing(Spacing.XS)
        
        self.spinbox = spinbox
        self.spinbox.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.spinbox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.spinbox.setFrame(False) 
        
        self.btn_up = QPushButton("▲")
        self.btn_down = QPushButton("▼")
        self.reset_btn = QPushButton("×")
        
        # FIX: Larger buttons and font size
        btn_style = f"""
            QPushButton {{
                background-color: {Palette.BG_DARK_3};
                border: 1px solid {Palette.DIVIDER};
                border-radius: 4px;
                color: {Palette.TEXT_MUTED};
                font-size: 14px; 
                padding: 0;
            }}
            QPushButton:hover {{ 
                border-color: {Palette.TEXT_SECONDARY}; 
                background-color: {Palette.BG_LIGHT}; 
                color: {Palette.TEXT};
            }}
            QPushButton:pressed {{ background-color: {Palette.BG_DARK_2}; }}
        """
        
        for b in (self.btn_up, self.btn_down, self.reset_btn):
            b.setFixedSize(28, 28) # FIX: Increased from 24 to 28
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(btn_style)
        
        # Reset button styled red on hover
        self.reset_btn.setStyleSheet(btn_style + f"QPushButton:hover {{ color: {Palette.ERROR}; border-color: {Palette.ERROR}; }}")
        
        self.btn_up.clicked.connect(self.spinbox.stepUp)
        self.btn_down.clicked.connect(self.spinbox.stepDown)
        
        arrows_layout = QVBoxLayout()
        arrows_layout.setContentsMargins(0, 0, 0, 0)
        arrows_layout.setSpacing(2)
        arrows_layout.addWidget(self.btn_up)
        arrows_layout.addWidget(self.btn_down)
        
        self.reset_btn.clicked.connect(
            lambda: self.spinbox.reset_to_default() 
                if hasattr(self.spinbox, 'reset_to_default') 
                else self.spinbox.setValue(0)
        )
        
        hlayout.addWidget(self.spinbox)
        hlayout.addLayout(arrows_layout)
        hlayout.addWidget(self.reset_btn)
        layout.addWidget(self.container)