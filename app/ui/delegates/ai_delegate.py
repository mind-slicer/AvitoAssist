from PyQt6.QtWidgets import QStyledItemDelegate, QStyle
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen, QFont
from app.ui.styles import Palette
import json

class AIDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index):
        painter.save()

        # 1. Получаем данные
        # Пытаемся взять текст напрямую (это может быть "VERY_BAD" или json)
        raw_data = index.data(Qt.ItemDataRole.DisplayRole)
        user_data = index.data(Qt.ItemDataRole.UserRole)
        
        verdict = "UNKNOWN"
        
        # Если в ячейке лежит JSON (иногда бывает), парсим его
        if raw_data and isinstance(raw_data, str) and raw_data.strip().startswith('{'):
            try:
                data = json.loads(raw_data)
                verdict = data.get("verdict", "UNKNOWN")
            except:
                verdict = raw_data
        # Если в UserRole лежит JSON (наш новый стандарт), берем оттуда
        elif user_data and isinstance(user_data, str) and user_data.strip().startswith('{'):
             try:
                data = json.loads(user_data)
                verdict = data.get("verdict", "UNKNOWN")
             except:
                pass
        else:
            # Иначе считаем, что текст ячейки — это и есть вердикт
            verdict = str(raw_data) if raw_data else "UNKNOWN"

        # Нормализация
        verdict = verdict.upper().strip()

        # 2. Маппинг цветов и текста
        bg_color = QColor(Palette.BG_DARK_3)
        text_color = QColor(Palette.TEXT_MUTED)
        display_text = verdict

        # Словарь перевода и стилей
        styles = {
            "GREAT_DEAL": ("💎 ОТЛИЧНО", QColor("#1e3a2a"), QColor(Palette.SUCCESS)),
            "GOOD":       ("✅ ХОРОШО",   QColor("#1a2e25"), QColor(Palette.SUCCESS)),
            "BAD":        ("❌ ПЛОХО",    QColor("#3a2a1e"), QColor(Palette.WARNING)),
            "VERY_BAD":   ("🚫 ОЧЕНЬ ПЛОХО",   QColor("#3a1e1e"), QColor(Palette.ERROR)),
            "SCAM":       ("🚫 СКАМ",     QColor("#3a1e1e"), QColor(Palette.ERROR)),
            "HARD_TO_SAY":("🤔 ЗАТРУДНЯЮСЬ",   QColor(Palette.BG_DARK_2), QColor(Palette.TEXT_SECONDARY)),
            "UNKNOWN":    ("❓ ...",      QColor(Palette.BG_DARK_3), QColor(Palette.TEXT_MUTED)),
        }

        # Пытаемся найти точное совпадение
        if verdict in styles:
            display_text, bg_color, text_color = styles[verdict]
        else:
            # Если точного нет, ищем частичное (на случай мусора в строке)
            for key, val in styles.items():
                if key in verdict:
                    display_text, bg_color, text_color = val
                    break

        # 3. Отрисовка
        rect = option.rect.adjusted(4, 4, -4, -4)

        # Фон выделения строки (если выбрана)
        if option.state & QStyle.StateFlag.State_Selected:
             painter.fillRect(option.rect, QColor(Palette.BG_DARK_2))

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Рисуем "таблетку" (badge)
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 4, 4)

        # Рисуем текст
        painter.setPen(QPen(text_color))
        font = QFont("Segoe UI", 9)
        font.setBold(True)
        painter.setFont(font)
        
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, display_text)

        painter.restore()