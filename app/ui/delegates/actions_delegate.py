from PyQt6.QtWidgets import QStyledItemDelegate
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QIcon, QPixmap
from app.ui.styles import Palette, Components # Подтяни пути к иконкам

class ActionsDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Загружаем иконки (пути проверь в components.py или загрузи свои)
        # Пока используем текст/символы если иконок нет под рукой
        self.trash_icon = "🗑️" 
        self.star_icon = "⭐"

    def paint(self, painter, option, index):
        painter.save()
        
        # Рисуем звездочку (слева) и корзину (справа) внутри ячейки
        # Простая реализация текстом для надежности
        rect = option.rect
        
        # Звезда
        star_rect = rect.adjusted(5, 0, -rect.width()//2, 0)
        painter.drawText(star_rect, Qt.AlignmentFlag.AlignCenter, self.star_icon)
        
        # Корзина
        trash_rect = rect.adjusted(rect.width()//2, 0, -5, 0)
        painter.drawText(trash_rect, Qt.AlignmentFlag.AlignCenter, self.trash_icon)
        
        painter.restore()

    def editorEvent(self, event, model, option, index):
        # Обработка кликов
        if event.type() == event.Type.MouseButtonRelease:
            click_x = event.pos().x()
            cell_x = option.rect.x()
            relative_x = click_x - cell_x
            
            # Если клик в правой половине -> удаление
            if relative_x > option.rect.width() / 2:
                # Сигналим таблице удалить строку
                # Т.к. делегат не имеет доступа к таблице напрямую,
                # лучше всего эмитить кастомный сигнал из таблицы, но тут можно хак:
                if hasattr(self.parent(), 'delete_row_requested'):
                    self.parent().delete_row_requested(index.row())
                return True
            
            # Если клик в левой -> избранное (пока заглушка)
            else:
                 pass
                 
        return False