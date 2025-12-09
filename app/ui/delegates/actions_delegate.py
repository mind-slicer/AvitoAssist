from PyQt6.QtWidgets import QStyledItemDelegate, QStyle
from PyQt6.QtCore import Qt, QPoint, QRect
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from app.ui.styles import Palette, Components

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
        
        item = index.data(Qt.ItemDataRole.UserRole)
        is_favorite = item.get('is_favorite', False) if isinstance(item, dict) else False
        
        rect = option.rect
        row = index.row()
        
        is_star_hovered = (self.hovered_row == row and self.hovered_side == 'star')
        is_trash_hovered = (self.hovered_row == row and self.hovered_side == 'trash')
        is_star_pressed = (self.pressed_row == row and self.pressed_side == 'star')
        is_trash_pressed = (self.pressed_row == row and self.pressed_side == 'trash')
        
        star_rect = QRect(rect.x() + 5, rect.y(), rect.width()//2 - 5, rect.height())
        trash_rect = QRect(rect.x() + rect.width()//2, rect.y(), rect.width()//2 - 5, rect.height())
        
        if is_star_pressed:
            painter.fillRect(star_rect, QColor(Palette.PRIMARY_DARK))
        elif is_star_hovered:
            painter.fillRect(star_rect, QColor(Palette.with_alpha(Palette.PRIMARY, 0.3)))
        
        if is_trash_pressed:
            painter.fillRect(trash_rect, QColor(Palette.with_alpha(Palette.ERROR, 0.6)))
        elif is_trash_hovered:
            painter.fillRect(trash_rect, QColor(Palette.with_alpha(Palette.ERROR, 0.3)))
        
        star_icon = self.star_icon_filled if is_favorite else self.star_icon_empty
        
        font = painter.font()
        original_size = font.pointSize()
        base_icon_size = original_size + 2
        
        if is_star_pressed:
            font.setPointSize(base_icon_size + 2)  # Еще +2 при нажатии
            painter.setFont(font)
            painter.setPen(QColor(Palette.WARNING))
        elif is_star_hovered:
            font.setPointSize(base_icon_size + 1)  # +1 при hover
            painter.setFont(font)
            painter.setPen(QColor(Palette.WARNING))
        else:
            font.setPointSize(base_icon_size)  # Базовый увеличенный размер
            painter.setFont(font)
            painter.setPen(QColor(Palette.TEXT))

        painter.drawText(star_rect, Qt.AlignmentFlag.AlignCenter, star_icon)

        # Корзина
        if is_trash_pressed:
            font.setPointSize(base_icon_size + 2)
            painter.setFont(font)
            painter.setPen(QColor(Palette.ERROR))
        elif is_trash_hovered:
            font.setPointSize(base_icon_size + 1)
            painter.setFont(font)
            painter.setPen(QColor(Palette.ERROR))
        else:
            font.setPointSize(base_icon_size)
            painter.setFont(font)
            painter.setPen(QColor(Palette.TEXT))

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