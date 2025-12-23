import json
from PyQt6.QtWidgets import QTableView, QHeaderView, QTableWidgetItem, QToolTip, QApplication, QStyledItemDelegate, QMessageBox
from PyQt6.QtCore import pyqtSignal, Qt, QUrl, QRect
from PyQt6.QtGui import QColor, QFont, QDesktopServices, QPainter, QCursor
from datetime import datetime, timedelta
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

class VerdictItem(QTableWidgetItem):
    SORT_ORDER = {
        "GREAT_DEAL": 10,
        "GOOD": 8,
        "BAD": 3,
        "SCAM": 1,
        "UNKNOWN": 0
    }

    def __init__(self, raw_json: str):
        super().__init__()
        self.raw_data = raw_json
        self.verdict = "UNKNOWN"
        self.reason = ""
        self.defects = False
        self.market_position = ""
        self._parse_and_set_display()
    
    def __lt__(self, other):
        if isinstance(other, VerdictItem):
            s1 = self.SORT_ORDER.get(self.verdict, 0)
            s2 = self.SORT_ORDER.get(other.verdict, 0)
            return s1 < s2
        return super().__lt__(other)

    def _parse_and_set_display(self):
        try:
            clean_json = self.raw_data.strip()

            if clean_json.startswith("```json") and clean_json.endswith("```"):
                clean_json = clean_json[7:-3].strip()
            elif clean_json.startswith("```") and clean_json.endswith("```"):
                clean_json = clean_json[3:-3].strip()
            elif "```json" in clean_json and "```" in clean_json:
                parts = clean_json.split("```json")
                if len(parts) > 1:
                    inner = parts[1].split("```")[0]
                    clean_json = inner.strip()
            elif "```" in clean_json:
                parts = clean_json.split("```")
                if len(parts) > 2:
                    clean_json = parts[1].strip()

            data = json.loads(clean_json)

            self.verdict = str(data.get("verdict", "UNKNOWN")).upper().strip()
            self.reason = str(data.get("reason", ""))
            self.defects = bool(data.get("defects", False))
            self.market_position = str(data.get("market_position", "")).lower()

        except Exception:
            # Fallback
            self.verdict = "UNKNOWN"
            self.reason = "Ошибка чтения ответа AI"
        
        v_map = {
            "GREAT_DEAL": "💎 ОТЛИЧНО",
            "GOOD": "✅ ХОРОШО",
            "BAD": "❌ ПЛОХО",
            "SCAM": "🚫 СКАМ",
            "UNKNOWN": "❓"
        }
        v_str = v_map.get(self.verdict, self.verdict)

        cell_text = v_str
        if self.defects: cell_text += " ⚠️"
        
        # Рынок стрелочками
        if self.market_position == "below_market": cell_text += " 📉"
        elif self.market_position == "overpriced": cell_text += " 📈"

        self.setText(cell_text)

        tooltip = f"""
        <b>ВЕРДИКТ: {v_str}</b>
        <hr>
        <b>📝 Анализ:</b><br>{self.reason}
        <br><br>
        """
        
        if self.market_position:
            m_text = "В рынке"
            if self.market_position == "below_market": m_text = "Ниже рынка (Выгодно)"
            elif self.market_position == "overpriced": m_text = "Выше рынка (Дорого)"
            tooltip += f"<b>📊 Позиция:</b> {m_text}<br>"
            
        if self.defects:
            tooltip += "<b>⚠️ Обнаружены дефекты!</b>"
        
        self.setToolTip(tooltip.strip())
        self.setData(Qt.ItemDataRole.UserRole, self.raw_data)
        self.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        font = QFont()
        font.setBold(True)
        self.setFont(font)

    def data(self, role):
        if role == Qt.ItemDataRole.ForegroundRole:
            if self.verdict == "GREAT_DEAL":
                return QColor(Palette.INFO)
            elif self.verdict == "GOOD":
                return QColor(Palette.SUCCESS)
            elif self.verdict == "BAD":
                return QColor(Palette.WARNING)
            elif self.verdict == "SCAM":
                return QColor(Palette.ERROR)
            else:
                return QColor(Palette.TEXT_MUTED)

        elif role == Qt.ItemDataRole.BackgroundRole:
            if self.verdict == "GREAT_DEAL":
                return QColor(Palette.with_alpha(Palette.INFO, 0.4))
            elif self.verdict == "GOOD":
                return QColor(Palette.with_alpha(Palette.SUCCESS, 0.4))
            elif self.verdict == "BAD":
                return QColor(Palette.with_alpha(Palette.WARNING, 0.4))
            elif self.verdict == "SCAM":
                return QColor(Palette.with_alpha(Palette.ERROR, 0.4))
            else:
                return QColor(Palette.BG_DARK_3)

        return super().data(role)

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
        source_index = self.proxy_model.mapToSource(index)
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
            verdict = item.get("verdict", "UNKNOWN")
            ai_json_str = item.get("ai_analysis", "{}")
            
            if isinstance(ai_json_str, str):
                try:
                    data = json.loads(ai_json_str)
                except:
                    data = {}
            else:
                data = ai_json_str if isinstance(ai_json_str, dict) else {}

            reason = data.get("reason", "Нет объяснения")
            m_pos = data.get("market_position", "Не определено")
            defects = "Да" if data.get("defects") else "Нет"
            
            pos_map = {"below_market": "Ниже рынка", "fair": "По рынку", "overpriced": "Дорого"}
            m_pos_ru = pos_map.get(m_pos, m_pos)

            report = (
                f"🤖 ВЕРДИКТ ИИ: {verdict}\n"
                f"{'-'*30}\n\n"
                f"📝 ОБЪЯСНЕНИЕ:\n{reason}\n\n"
                f"📊 ПОЗИЦИЯ НА РЫНКЕ: {m_pos_ru}\n"
                f"⚠️ ДЕФЕКТЫ/РИСКИ: {defects}\n"
            )
            
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle(f"Анализ элемента {item.get('id')}...")
            msg_box.setText(report)
            msg_box.setIcon(QMessageBox.Icon.Information)
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