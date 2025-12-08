import json
from PyQt6.QtWidgets import QTableView, QHeaderView, QTableWidgetItem
from PyQt6.QtCore import QSortFilterProxyModel, Qt, QRegularExpression, QUrl
from PyQt6.QtGui import QColor, QFont, QDesktopServices
from datetime import datetime, timedelta
from app.ui.models.results_model import ResultsModel
from app.ui.delegates.ai_delegate import AIDelegate
from app.ui.delegates.actions_delegate import ActionsDelegate
from app.ui.styles import Components, Palette
from app.ui.models.proxy_model import CustomSortFilterProxyModel

class PriceItem(QTableWidgetItem):
    def __init__(self, value: int):
        self.value = int(value or 0)
        formatted = f"{self.value:,}".replace(',', ' ')
        super().__init__(formatted)
    
    def __lt__(self, other):
        if isinstance(other, PriceItem):
            return self.value < other.value
        return super().__lt__(other)

class TitleItem(QTableWidgetItem):
    def __init__(self, title: str, link: str):
        super().__init__(title)
        self.title_text = title.lower()
        self.link = link
        self.setData(Qt.ItemDataRole.UserRole, link)

    def __lt__(self, other):
        if isinstance(other, TitleItem):
            return self.title_text < other.title_text
        return super().__lt__(other)

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

class DateItem(QTableWidgetItem):
    def __init__(self, text: str):
        super().__init__(text)
        self._sort_ts = self._parse_to_ts(text)

    @staticmethod
    def _parse_to_ts(text: str) -> datetime:
        s = (text or "").strip().lower()
        now = datetime.now()
        if not s: return datetime.min
        
        if "сегодня" in s:
            try:
                time_part = s.split(" в ")[-1].strip()
                h, m = map(int, time_part.split(":"))
                return now.replace(hour=h, minute=m, second=0, microsecond=0)
            except: return now
        if "вчера" in s:
            try:
                time_part = s.split(" в ")[-1].strip()
                h, m = map(int, time_part.split(":"))
                d = now - timedelta(days=1)
                return d.replace(hour=h, minute=m, second=0, microsecond=0)
            except: return now - timedelta(days=1)
        
        return datetime.min

    def __lt__(self, other):
        if isinstance(other, DateItem):
            return self._sort_ts < other._sort_ts
        return super().__lt__(other)

class VerdictItem(QTableWidgetItem):
    SORT_ORDER = {
        "GREAT_DEAL": 4,
        "GOOD": 3,
        "UNKNOWN": 2,
        "BAD": 1,
        "SCAM": 0
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
            s1 = self.SORT_ORDER.get(self.verdict, 2)
            s2 = self.SORT_ORDER.get(other.verdict, 2)
            return s1 < s2
        return super().__lt__(other)

    def _parse_and_set_display(self):
        try:
            clean_json = self.raw_data.strip()

            # ИСПРАВЛЕНО: Корректная обработка markdown-блоков
            if clean_json.startswith("```json") and clean_json.endswith("```"):
                clean_json = clean_json[7:-3].strip()
            elif clean_json.startswith("```") and clean_json.endswith("```"):
                clean_json = clean_json[3:-3].strip()
            elif "```json" in clean_json and "```" in clean_json:
                # Обработка случая, когда блок находится в середине текста
                parts = clean_json.split("```json")
                if len(parts) > 1:
                    inner = parts[1].split("```")[0]
                    clean_json = inner.strip()
            elif "```" in clean_json:
                # Обработка обычного markdown-блока
                parts = clean_json.split("```")
                if len(parts) > 2:  # Есть открывающий и закрывающий маркеры
                    clean_json = parts[1].strip()

            data = json.loads(clean_json)

            self.verdict = str(data.get("verdict", "UNKNOWN")).upper().strip()
            self.reason = str(data.get("reason", ""))
            self.defects = bool(data.get("defects", False))
            m_pos = str(data.get("market_position", "")).lower()
            self.market_position = m_pos

        except (json.JSONDecodeError, AttributeError, TypeError, ValueError):
            self.verdict = "UNKNOWN"
            self.reason = str(self.raw_data)[:100]
            m_pos = ""
            self.market_position = ""

        # ✅ НОВОЕ: Улучшенный формат с эмодзи
        if self.verdict == "GREAT_DEAL":
            display_text = "🎯 ОТЛИЧНАЯ СДЕЛКА"
        elif self.verdict == "GOOD":
            display_text = "✅ ХОРОШО"
        elif self.verdict == "BAD":
            display_text = "⚠️ ПЛОХО"
        elif self.verdict == "SCAM":
            display_text = "🚫 СКАМ"
        else:
            display_text = "❓ НЕИЗВЕСТНО"

        # Добавляем индикаторы рынка
        if m_pos == "below_market":
            display_text += " 📉"
        elif m_pos == "overpriced":
            display_text += " 📈"

        # Добавляем предупреждение о дефектах
        if self.defects:
            display_text += " ⚠️"

        self.setText(display_text)

        tooltip_parts = []
    
        # Блок 1: Вердикт + Причина (одним блоком)
        verdict_block = f"Вердикт: {self.verdict}"
        if self.reason:
            verdict_block += f"\nПричина: {self.reason}"
        tooltip_parts.append(verdict_block)
        
        # Блок 2: Позиция в таблице
        if self.market_position:
            if self.market_position == "below_market":
                tooltip_parts.append("Позиция в таблице: Ниже среднего 📉")
            elif self.market_position == "fair":
                tooltip_parts.append("Позиция в таблице: Средняя цена →")
            elif self.market_position == "overpriced":
                tooltip_parts.append("Позиция в таблице: Выше среднего 📈")
        
        # Блок 3: Позиция на рынке (RAG заглушка)
        tooltip_parts.append("Позиция на рынке: Мало данных")
        
        # Блок 4: Дефекты
        if self.defects:
            tooltip_parts.append("⚠️ Есть дефекты или проблемы")
        
        # Собираем с двойным \n между БЛОКАМИ (не внутри блоков)
        tooltip = "\n".join(tooltip_parts)
        
        self.setToolTip(tooltip)
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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.source_model = ResultsModel()
        self.proxy_model = CustomSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.source_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

        self.proxy_model.setFilterKeyColumn(-1) 
        self.setModel(self.proxy_model)
        self.model = self.source_model 
        self.setSortingEnabled(True)
        self.setMouseTracking(True)
        
        # --- Делегаты ---
        self.ai_delegate = AIDelegate()
        self.actions_delegate = ActionsDelegate(self) # передаем self как parent
        
        self.setItemDelegateForColumn(7, self.ai_delegate) # AI (col 7)
        self.setItemDelegateForColumn(0, self.actions_delegate) # Actions (col 0)

        # --- Стили ---
        self.setShowGrid(True) # Включаем сетку (разделители) - ИСПРАВЛЕНИЕ 2
        self.setGridStyle(Qt.PenStyle.SolidLine)
        
        # --- Ширина колонок (ИСПРАВЛЕНИЕ 7) ---
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        # 0: Actions (fixed, small)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(0, 60)
        
        # 1: ID (fixed)
        self.setColumnWidth(1, 100)

        # 2: Price (fixed)
        self.setColumnWidth(2, 90)

        # 3: Title (stretch - основное место)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.setColumnWidth(3, 400)

        # 4: City
        self.setColumnWidth(4, 120)

        # 5: Date
        self.setColumnWidth(5, 100)

        # 6: Desc (Interactive - можно растягивать)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch) 

        # 7: AI
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(7, 140)

        # Обработка двойного клика (ИСПРАВЛЕНИЕ 4 и 7)
        self.doubleClicked.connect(self.on_double_click)

    def filter_data(self, text, column_index):
        # 1. Устанавливаем наш кастомный тип фильтра
        self.proxy_model.setFilterType(column_index)
        
        # 2. Устанавливаем текст (это запустит filterAcceptsRow)
        self.proxy_model.setFilterRegularExpression(text)

    def delete_row_requested(self, row):
        """Вызывается из делегата"""
        item = self.model.get_item(row)
        if item:
            # Тут можно эмитить сигнал наружу, чтобы удалить из базы/файла
            # self.item_deleted.emit(item['id']) 
            self.model.remove_row(row)

    def on_double_click(self, index):
        row = index.row()
        col = index.column()
        item = self.model.get_item(row)
        
        # Клик по заголовку (col 3) -> Открыть ссылку
        if col == 3:
            link = item.get('link')
            if link:
                QDesktopServices.openUrl(QUrl(link))
        
        # Клик по описанию (col 6) -> Показать полное (можно через QMessageBox)
        if col == 6:
            from PyQt6.QtWidgets import QMessageBox
            desc = item.get('description', 'Нет описания')
            QMessageBox.information(self, "Описание", desc)

    def mouseMoveEvent(self, event):
        # Меняем курсор на руку над ссылкой (колонка 3)
        index = self.indexAt(event.pos())
        if index.isValid() and index.column() == 3:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def add_items(self, items):
        self.source_model.add_items(items)
        # Автоскролл вниз, если нужно
        if self.model.rowCount() > 0:
            self.scrollToBottom()

    def update_ai_column(self, row_idx, ai_json):
        self.model.update_ai_verdict(row_idx, ai_json)