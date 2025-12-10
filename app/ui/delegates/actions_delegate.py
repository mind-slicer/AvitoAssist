from PyQt6.QtWidgets import QStyledItemDelegate, QStyle
from PyQt6.QtCore import Qt, QPoint, QRect
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from app.ui.styles import Palette, Components, Typography

class ActionsDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.trash_icon = "❌"
        self.star_icon_empty = "🔖"
        self.star_icon_filled = "📌"
        
        self.hovered_row = -1
        self.hovered_side = None
        self.pressed_row = -1
        self.pressed_side = None

    def paint(self, painter, option, index):
        painter.save()
        
        # Получаем данные
        item = index.data(Qt.ItemDataRole.UserRole)
        is_favorite = item.get('is_favorite', False) if isinstance(item, dict) else False
        
        rect = option.rect
        row = index.row()
        
        # Логика ховера/нажатия
        is_star_hovered = (self.hovered_row == row and self.hovered_side == 'star')
        is_trash_hovered = (self.hovered_row == row and self.hovered_side == 'trash')
        
        # Зоны клика (делим ячейку пополам)
        star_rect = QRect(rect.left(), rect.top(), rect.width()//2, rect.height())
        trash_rect = QRect(rect.left() + rect.width()//2, rect.top(), rect.width()//2, rect.height())
        
        # --- ОТРИСОВКА ФОНОВ КНОПОК ---
        if is_star_hovered:
            painter.fillRect(star_rect, QColor(Palette.with_alpha(Palette.WARNING, 0.15)))
        
        if is_trash_hovered:
            painter.fillRect(trash_rect, QColor(Palette.with_alpha(Palette.ERROR, 0.15)))

        # --- НАСТРОЙКА ШРИФТА (Ключевой момент!) ---
        # Игнорируем шрифт таблицы (Monospace) и берем UI шрифт для иконок
        icon_font = QFont(Typography.UI) 
        icon_font.setPixelSize(16) # Фиксированный размер иконки
        # Для эмодзи/символов важно, чтобы шрифт их поддерживал
        icon_font.setStyleHint(QFont.StyleHint.SansSerif) 
        painter.setFont(icon_font)

        # --- РИСУЕМ ЗВЕЗДУ ---
        if is_favorite:
            painter.setPen(QColor(Palette.WARNING)) # Желтая/Оранжевая
            icon = self.star_icon_filled
        else:
            # Если не избрано - серый цвет, но при наведении - оранжевый
            color = Palette.WARNING if is_star_hovered else Palette.TEXT_MUTED
            painter.setPen(QColor(color))
            icon = self.star_icon_empty
            
        painter.drawText(star_rect, Qt.AlignmentFlag.AlignCenter, icon)

        # --- РИСУЕМ КОРЗИНУ ---
        color = Palette.ERROR if is_trash_hovered else Palette.TEXT_MUTED
        painter.setPen(QColor(color))
        painter.drawText(trash_rect, Qt.AlignmentFlag.AlignCenter, self.trash_icon)

        painter.restore()

    def editorEvent(self, event, model, option, index):
        row = index.row()
        
        if event.type() == event.Type.MouseMove:
            click_x = event.pos().x()
            cell_x = option.rect.x()
            relative_x = click_x - cell_x
            
            old_hovered_row = self.hovered_row
            old_hovered_side = self.hovered_side
            
            self.hovered_row = row
            if relative_x > option.rect.width() / 2:
                self.hovered_side = 'trash'
            else:
                self.hovered_side = 'star'
            
            if old_hovered_row != self.hovered_row or old_hovered_side != self.hovered_side:
                if self.parent():
                    self.parent().viewport().update()
            
            return False
        
        if event.type() == event.Type.MouseButtonPress:
            click_x = event.pos().x()
            cell_x = option.rect.x()
            relative_x = click_x - cell_x
            
            self.pressed_row = row
            if relative_x > option.rect.width() / 2:
                self.pressed_side = 'trash'
            else:
                self.pressed_side = 'star'
            
            if self.parent():
                self.parent().viewport().update()
            return True
        
        if event.type() == event.Type.MouseButtonRelease:
            click_x = event.pos().x()
            cell_x = option.rect.x()
            relative_x = click_x - cell_x
            
            proxy_row = index.row()
            
            self.pressed_row = -1
            self.pressed_side = None
            
            if relative_x > option.rect.width() / 2:
                if hasattr(self.parent(), 'delete_row_requested'):
                    self.parent().delete_row_requested(proxy_row)
            else:
                if hasattr(self.parent(), 'toggle_favorite_requested'):
                    self.parent().toggle_favorite_requested(proxy_row)
            
            if self.parent():
                self.parent().viewport().update()
            return True
        
        return False