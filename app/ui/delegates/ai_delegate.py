from PyQt6.QtWidgets import QStyledItemDelegate
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen, QFont
from app.ui.styles import Palette

class AIDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index):
        painter.save()
        
        # Получаем данные
        item = index.data(Qt.ItemDataRole.UserRole)
        verdict = item.get('verdict', 'UNKNOWN') if item else 'UNKNOWN'
        
        # Настройка цветов в зависимости от вердикта
        bg_color = QColor(Palette.BG_DARK_3)
        text_color = QColor(Palette.TEXT_MUTED)
        text = verdict

        if verdict == 'GREAT_DEAL':
            bg_color = QColor("#1e3a2a") # Dark Green
            text_color = QColor(Palette.SUCCESS)
            text = "🎯 GREAT DEAL"
        elif verdict == 'GOOD':
            bg_color = QColor("#1a2e25")
            text_color = QColor(Palette.SUCCESS)
            text = "✅ GOOD"
        elif verdict == 'BAD':
            bg_color = QColor("#3a2a1e") # Dark Orange
            text_color = QColor(Palette.WARNING)
            text = "⚠️ BAD"
        elif verdict == 'SCAM':
            bg_color = QColor("#3a1e1e") # Dark Red
            text_color = QColor(Palette.ERROR)
            text = "🚫 SCAM"

        # Рисуем фон (прямоугольник с закруглением)
        rect = option.rect.adjusted(4, 4, -4, -4)
        
        # Если ячейка выбрана - подсвечиваем фон стандартно, а поверх рисуем бейдж
        if option.state and 4: # State_Selected
             painter.fillRect(option.rect, QColor(Palette.BG_DARK_2))

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 4, 4)

        # Рисуем текст
        painter.setPen(QPen(text_color))
        font = QFont("Segoe UI", 9) 
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

        painter.restore()