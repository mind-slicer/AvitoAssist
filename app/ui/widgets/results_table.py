import json
from PyQt6.QtWidgets import QTableView, QHeaderView, QTableWidgetItem, QToolTip, QApplication, QStyledItemDelegate, QMessageBox
from PyQt6.QtCore import pyqtSignal, Qt, QUrl, QRect
from PyQt6.QtGui import QColor, QFont, QDesktopServices, QPainter, QCursor
from app.ui.models.results_model import ResultsModel
from app.ui.delegates.ai_delegate import AIDelegate
from app.ui.delegates.actions_delegate import ActionsDelegate
from app.ui.styles import Components, Palette
from app.ui.models.proxy_model import CustomSortFilterProxyModel


class TitleDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_table = parent

    def paint(self, painter: QPainter, option, index):
        painter.save()
        
        item_data = index.data(Qt.ItemDataRole.UserRole)
        if not item_data:
            painter.restore()
            return
        
        title = item_data.get('title', 'No Title')
        seller_id = item_data.get('seller_id', '')
        
        rect = option.rect
        painter.setClipRect(rect)
        
        padding_x = 5
        padding_y = 5
        text_rect = rect.adjusted(padding_x, padding_y, -padding_x, -padding_y)
        
        title_font = QFont(option.font)
        title_font.setBold(True)
        title_font.setPointSize(10)
        
        painter.setFont(title_font)
        painter.setPen(QColor("#4a90e2"))
        
        fm = painter.fontMetrics()
        title_rect = painter.boundingRect(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, title)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, 
                        fm.elidedText(title, Qt.TextElideMode.ElideRight, text_rect.width()))
        
        title_height = fm.height()
        
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, title)
        
        if seller_id:
            id_font = QFont(option.font)
            id_font.setPointSize(8) # Чуть меньше
            painter.setFont(id_font)
            
            # Используем явный серый цвет, чтобы не зависеть от Palette
            painter.setPen(QColor(128, 128, 128))
            
            id_text = f"Seller ID: {seller_id}"
            
            # Смещаем вниз на высоту заголовка + отступ
            id_y = text_rect.top() + title_height + 4
            
            # Проверяем, влезает ли ID в ячейку
            if id_y + 10 < text_rect.bottom():
                id_rect = QRect(text_rect.left(), id_y, text_rect.width(), 15)
                painter.drawText(id_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, id_text)
            
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == event.Type.MouseButtonRelease:
            item_data = index.data(Qt.ItemDataRole.UserRole)
            if item_data:
                seller_id = item_data.get('seller_id', '')
                
                if seller_id:
                    click_y = event.position().y() - option.rect.top()
                    
                    if click_y > 20: 
                        QApplication.clipboard().setText(seller_id)
                        QToolTip.showText(QCursor.pos(), f"ID {seller_id} скопирован!", option.widget)
                        return True
                    
        return super().editorEvent(event, model, option, index)

class ConditionItem(QTableWidgetItem):
    def __init__(self, text: str):
        super().__init__(text)
        t = (text or "").lower()
        if "нов" in t: key = 3
        elif "отл" in t or "идеал" in t: key = 2
        elif "б/у" in t or "бу" in t: key = 1
        else: key = 0
        self._sort_key = key

    def __lt__(self, other):
        if isinstance(other, ConditionItem):
            return self._sort_key < other._sort_key
        return super().__lt__(other)

class ResultsTable(QTableView):
    item_favorited = pyqtSignal(str, bool)
    item_deleted = pyqtSignal(str)
    analyze_item_requested = pyqtSignal(dict)
    addmemory_item_requested = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(Components.table())
        self.setAlternatingRowColors(True)
        self.source_model = ResultsModel()
        self.proxy_model = CustomSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.source_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

        self.proxy_model.setSortRole(Qt.ItemDataRole.EditRole)
        self.proxy_model.setFilterKeyColumn(-1)

        self.setModel(self.proxy_model)
        self.model = self.source_model 
        
        self.setSortingEnabled(True)
        self.setMouseTracking(True)
        
        # --- Делегаты ---
        self.ai_delegate = AIDelegate()
        self.actions_delegate = ActionsDelegate(self)
        self.title_delegate = TitleDelegate(self)
        
        self.setItemDelegateForColumn(0, self.actions_delegate)
        self.setItemDelegateForColumn(3, self.title_delegate)
        self.setItemDelegateForColumn(9, self.ai_delegate)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.on_row_context_menu)

        self.setShowGrid(True)
        self.setGridStyle(Qt.PenStyle.SolidLine)
        
        self.verticalHeader().setDefaultSectionSize(50)

        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(0, 70)
        self.setColumnWidth(1, 100)
        self.setColumnWidth(2, 90)
        
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.setColumnWidth(3, 400)
        
        self.setColumnWidth(4, 70)
        self.setColumnWidth(5, 100)
        self.setColumnWidth(6, 100)
        self.setColumnWidth(7, 120)
        
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
        
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(9, 140)

        self.doubleClicked.connect(self.on_double_click)

    def filter_data(self, text, column_index):
        self.proxy_model.setFilterType(column_index)
        self.proxy_model.setFilterRegularExpression(text)

    def toggle_favorite_requested(self, proxy_row):
        proxy_index = self.proxy_model.index(proxy_row, 0)
        source_index = self.proxy_model.mapToSource(proxy_index)
        source_row = source_index.row()
        
        item = self.source_model.get_item(source_row)
        if item:
            item_id = item.get('id', '')
            current_favorite = item.get('is_favorite', False)
            new_favorite = not current_favorite
            
            item['is_favorite'] = new_favorite
            
            if item_id:
                self.item_favorited.emit(item_id, new_favorite)
            
            self.viewport().update()

    def delete_row_requested(self, proxy_row):
        proxy_index = self.proxy_model.index(proxy_row, 0)
        source_index = self.proxy_model.mapToSource(proxy_index)
        source_row = source_index.row()

        item = self.source_model.get_item(source_row)
        if item:
            item_id = item.get('id', '')
            if item_id:
                self.item_deleted.emit(item_id)

            self.source_model.remove_row(source_row)

            if hasattr(self.actions_delegate, 'hovered_row'):
                self.actions_delegate.hovered_row = -1
                self.actions_delegate.hovered_side = None
                self.actions_delegate.pressed_row = -1
                self.actions_delegate.pressed_side = None

            self.viewport().update()

    def on_double_click(self, index):
        col = index.column()
        # Получаем данные через прокси
        proxy_index = self.proxy_model.index(index.row(), 0)
        source_index = self.proxy_model.mapToSource(proxy_index)
        source_row = source_index.row()
        item = self.source_model.get_item(source_row)
        
        if not item: return

        if col == 3:
            link = item.get('link')
            if link: QDesktopServices.openUrl(QUrl(link))

        elif col == 8:
            desc = item.get('description', 'Нет описания')
            QMessageBox.information(self, "Описание", desc)
        
        elif col == 9:
            # Пытаемся найти данные анализа в разных полях
            ai_data = {}
            
            # Вариант 1: Поле 'ai' (словарь)
            if isinstance(item.get('ai'), dict):
                ai_data = item['ai']
            # Вариант 2: Поле 'ai_analysis' (строка или словарь)
            elif item.get('ai_analysis'):
                raw = item['ai_analysis']
                if isinstance(raw, dict):
                    ai_data = raw
                elif isinstance(raw, str):
                    try:
                        import re
                        # Ищем JSON блок
                        match = re.search(r'\{.*\}', raw, re.DOTALL)
                        if match:
                            ai_data = json.loads(match.group(0))
                    except:
                        pass
            
            # Если данных нет, но есть сырой вердикт в ячейке
            if not ai_data:
                # Пытаемся вытащить хотя бы вердикт из самого айтема
                ai_data = {
                    "verdict": item.get("verdict", "UNKNOWN"),
                    "reason": item.get("ai_reason") or item.get("reason", "Нет данных"),
                    "thinking": item.get("ai_thinking") or item.get("thinking", "")
                }

            verdict = str(ai_data.get("verdict", "UNKNOWN")).upper()
            reason = ai_data.get("reason", "Нет объяснения")
            thinking = ai_data.get("thinking", "")
            defects = ai_data.get("defects", False)
            
            # Перевод для отчета
            v_map = {
                "GREAT_DEAL": "💎 ОТЛИЧНО",
                "GOOD": "✅ ХОРОШО",
                "BAD": "❌ ПЛОХО",
                "VERY_BAD": "🚫 ОЧЕНЬ ПЛОХО",
                "SCAM": "🚫 СКАМ",
                "HARD_TO_SAY": "🤔 ЗАТРУДНЯЮСЬ"
            }
            v_ru = v_map.get(verdict, verdict)

            report = f"<h2 style='color:#4a90e2; margin-bottom:5px'>🤖 ВЕРДИКТ: {v_ru}</h2>"
            
            if defects:
                report += "<div style='background-color:#3a1e1e; color:#ff4d4f; padding:8px; border-radius:4px; margin:10px 0;'><b>⚠️ ВНИМАНИЕ: Обнаружены дефекты или риски!</b></div>"

            report += f"<h3 style='color:#ccc'>📝 Заключение:</h3><p style='font-size:14px; line-height:1.4'>{reason}</p>"
            
            if thinking:
                # Экранируем переносы строк для HTML
                thinking_html = thinking.replace("\n", "<br>")
                report += "<hr style='border-color:#444'><h3 style='color:#aaa'>💭 Ход мыслей:</h3>"
                report += f"<div style='color:#888; font-style:italic; font-size:13px; background-color:#222; padding:10px; border-radius:5px'>{thinking_html}</div>"

            msg_box = QMessageBox(self)
            msg_box.setWindowTitle(f"Анализ ID: {item.get('id')}")
            msg_box.setTextFormat(Qt.TextFormat.RichText)
            msg_box.setText(report)
            msg_box.exec()

    def mouseMoveEvent(self, event):
        index = self.indexAt(event.pos())

        if hasattr(self.actions_delegate, 'hovered_row'):
            old_row = self.actions_delegate.hovered_row
            old_side = self.actions_delegate.hovered_side

            if index.isValid() and index.column() == 0:
                cell_rect = self.visualRect(index)
                relative_x = event.pos().x() - cell_rect.x()

                self.actions_delegate.hovered_row = index.row()
                if relative_x > cell_rect.width() / 2:
                    self.actions_delegate.hovered_side = 'trash'
                else:
                    self.actions_delegate.hovered_side = 'star'
            else:
                self.actions_delegate.hovered_row = -1
                self.actions_delegate.hovered_side = None

            if old_row != self.actions_delegate.hovered_row or old_side != self.actions_delegate.hovered_side:
                self.viewport().update()

        if index.isValid() and index.column() == 3:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

        super().mouseMoveEvent(event)

    def on_row_context_menu(self, pos):
        """Контекстное меню для строки таблицы"""
        index = self.indexAt(pos)
        if not index.isValid():
            return

        # Получить элемент
        proxy_index = self.proxy_model.index(index.row(), 0)
        source_index = self.proxy_model.mapToSource(proxy_index)
        source_row = source_index.row()
        item = self.source_model.get_item(source_row)

        if not item:
            return

        from PyQt6.QtWidgets import QMenu
        from app.ui.styles import Palette

        menu = QMenu(self)
        menu.setStyleSheet(f"background: {Palette.BG_DARK_2}; color: {Palette.TEXT};")

        act_analyze = menu.addAction("🔍 Проанализировать")
        act_addmemory = menu.addAction("🧠 Добавить в память ИИ")

        action = menu.exec(self.mapToGlobal(pos))

        if action == act_analyze:
            self.analyze_item_requested.emit(item)
        elif action == act_addmemory:
            self.addmemory_item_requested.emit(item)

    def leaveEvent(self, event):
        if hasattr(self.actions_delegate, 'hovered_row'):
            self.actions_delegate.hovered_row = -1
            self.actions_delegate.hovered_side = None
            self.viewport().update()
        super().leaveEvent(event)

    def add_items(self, items):
        self.source_model.add_items(items)

    def update_ai_column(self, row_idx, ai_json):
        self.model.update_ai_verdict(row_idx, ai_json)