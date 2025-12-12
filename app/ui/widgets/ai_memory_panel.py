from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QScrollArea, QFrame, QSizePolicy, QToolTip
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPropertyAnimation, QEvent
from PyQt6.QtGui import QColor

# Импортируем стили проекта (предполагаем, что они есть согласно структуре)
from app.ui.styles import Components, Palette, Typography, Spacing

class ChunkCard(QFrame):
    """
    Карточка для отображения одного чанка памяти.
    Визуализирует статус: PENDING, INITIALIZING, READY, COMPRESSED.
    """
    
    deleted = pyqtSignal(int)  # сигнал удаления (chunk_id)
    
    def __init__(self, chunk_data: dict, parent=None):
        super().__init__(parent)
        self.chunk_data = chunk_data
        self.chunk_id = chunk_data.get('id')
        self.status = chunk_data.get('status')
        
        # Базовый стиль карточки
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Palette.BG_LIGHT};
                border: 1px solid {Palette.BORDER_PRIMARY};
                border-radius: 8px;
            }}
        """)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        
        self._init_ui()
        self._update_appearance()
    
    def _init_ui(self):
        """Строит структуру карточки"""
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 12, 12, 12)
        self.layout.setSpacing(8)
        
        # --- HEADER ---
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        
        # Иконка типа/статуса
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(24, 24)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("font-size: 16px; border: none; background: transparent;")
        header_layout.addWidget(self.icon_label)
        
        # Заголовок и статус
        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)
        
        self.title_label = QLabel()
        self.title_label.setStyleSheet(f"font-weight: bold; color: {Palette.TEXT}; font-size: 13px; border: none;")
        self.title_label.setWordWrap(True)
        title_layout.addWidget(self.title_label)
        
        self.status_label = QLabel()
        self.status_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 11px; border: none;")
        title_layout.addWidget(self.status_label)
        
        header_layout.addLayout(title_layout, stretch=1)
        
        # Кнопка удаления (крестик)
        self.delete_btn = QPushButton("✕")
        self.delete_btn.setFixedSize(24, 24)
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {Palette.TEXT_MUTED};
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {Palette.ERROR};
                background: rgba(255, 0, 0, 0.1);
                border-radius: 4px;
            }}
        """)
        self.delete_btn.clicked.connect(self._on_delete)
        header_layout.addWidget(self.delete_btn)
        
        self.layout.addLayout(header_layout)
        
        # --- CONTENT AREA ---
        self.content_container = QWidget()
        self.content_container.setStyleSheet("background: transparent; border: none;")
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(4, 0, 0, 0)
        self.content_layout.setSpacing(6)
        self.layout.addWidget(self.content_container)
    
    def _update_appearance(self):
        """Обновляет UI в зависимости от данных и статуса"""
        self.status = self.chunk_data.get('status')
        title = self.chunk_data.get('title') or f"Chunk #{self.chunk_id}"
        chunk_type = self.chunk_data.get('chunk_type', 'UNKNOWN')
        
        self.title_label.setText(title)
        
        # Очистка контента перед перерисовкой
        self._clear_content()
        
        if self.status == 'PENDING':
            self._render_pending()
        elif self.status == 'INITIALIZING':
            self._render_initializing()
        elif self.status == 'READY':
            self._render_ready(chunk_type)
        elif self.status == 'COMPRESSED':
            self._render_compressed()
        else:
            self.status_label.setText(f"Status: {self.status}")
            self.icon_label.setText("❓")

    def _render_pending(self):
        self.icon_label.setText("⏳")
        self.status_label.setText("В ожидании обработки...")
        self.delete_btn.setVisible(True) # Можно удалить даже если не готово

    def _render_initializing(self):
        self.icon_label.setText("⚙️")
        progress = self.chunk_data.get('progress_percent', 0)
        self.status_label.setText(f"Формирование знаний... {progress}%")
        self.delete_btn.setVisible(False) # Нельзя удалить во время генерации
        
        # Прогресс бар
        p_bar = QFrame()
        p_bar.setFixedHeight(4)
        p_bar.setStyleSheet(f"background: {Palette.BG_DARK}; border-radius: 2px;")
        
        fill = QFrame(p_bar)
        fill.setFixedHeight(4)
        width_pct = min(max(progress, 5), 100) # минимум 5% чтобы было видно
        # Note: реальная ширина устанавливается динамически, здесь упрощение через qss или layout
        # Для простоты используем stylesheet на самом виджете-заполнителе, 
        # но в Qt сложно задать ширину в % через CSS для вложенного виджета без Layout.
        # Сделаем через QProgressBar для надежности или просто текст.
        
        # Упрощенный вариант - текстовый прогресс или стиль
        # Но добавим визуальный бар через layout
        bar_container = QWidget()
        bar_layout = QHBoxLayout(bar_container)
        bar_layout.setContentsMargins(0,0,0,0)
        bar_layout.setSpacing(0)
        
        fill_widget = QWidget()
        fill_widget.setStyleSheet(f"background-color: {Palette.PRIMARY}; border-radius: 2px;")
        
        empty_widget = QWidget()
        empty_widget.setStyleSheet("background: transparent;")
        
        bar_layout.addWidget(fill_widget, stretch=width_pct)
        bar_layout.addWidget(empty_widget, stretch=100-width_pct)
        
        p_bar_wrapper = QFrame()
        p_bar_wrapper.setFixedHeight(6)
        p_bar_wrapper.setStyleSheet(f"background: {Palette.BG_DARK}; border-radius: 3px; border: none;")
        wrapper_layout = QVBoxLayout(p_bar_wrapper)
        wrapper_layout.setContentsMargins(0,0,0,0)
        wrapper_layout.addWidget(bar_container)
        
        self.content_layout.addWidget(p_bar_wrapper)

    def _render_ready(self, chunk_type):
        self.icon_label.setText("✓")
        
        # Дата обновления
        # --- ИСПРАВЛЕНИЕ: Показываем дату И ВРЕМЯ ---
        raw_date = self.chunk_data.get('last_updated', '')
        if len(raw_date) >= 16:
            # Преобразуем YYYY-MM-DDTHH:MM... -> DD-MM-YYYY HH:MM
            last_upd = f"{raw_date[11:16]} • {raw_date[8:10]}.{raw_date[5:7]}.{raw_date[:4]}"
        else:
            last_upd = raw_date

        size_bytes = self.chunk_data.get('original_size', 0)
        size_kb = size_bytes / 1024
        self.status_label.setText(f"Активен • {last_upd} • {size_kb:.1f} KB")
        self.delete_btn.setVisible(True)
        
        # Контент (Summary)
        summary = self.chunk_data.get('summary')
        
        # Если summary нет в корне, попробуем достать из JSON content
        if not summary and self.chunk_data.get('content'):
            import json
            try:
                data = json.loads(self.chunk_data['content'])
                summary = data.get('summary')
                if not summary and isinstance(data.get('analysis'), dict):
                    summary = data['analysis'].get('summary')
            except:
                pass
        
        if summary:
            lbl = QLabel(str(summary))
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {Palette.TEXT}; font-size: 12px; line-height: 1.4; border: none;")
            # Ограничим высоту текста, если он огромный
            lbl.setMaximumHeight(100) 
            self.content_layout.addWidget(lbl)
            
            # Если это PRODUCT, добавим метрики цены если есть
            # (Можно расширять логику рендеринга по типу)
        else:
            lbl = QLabel("Нет краткого описания.")
            lbl.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-style: italic; font-size: 11px; border: none;")
            self.content_layout.addWidget(lbl)

    def _render_compressed(self):
        self.icon_label.setText("📦")
        
        raw_date = self.chunk_data.get('last_updated', '')
        if len(raw_date) >= 16:
            last_upd = f"{raw_date[11:16]} • {raw_date[8:10]}.{raw_date[5:7]}.{raw_date[:4]}"
        else:
            last_upd = raw_date
        
        orig_size = self.chunk_data.get('original_size', 0)
        comp_size = self.chunk_data.get('compressed_size', 0)
        
        saved = 0
        if orig_size > 0:
            saved = int((1 - comp_size/orig_size) * 100)
            
        self.status_label.setText(f"Сжат (экономия {saved}%) • {last_upd}")
        self.delete_btn.setVisible(True)
        
        # Показываем сжатый контент (он обычно не читаем для человека, но покажем факт наличия)
        lbl = QLabel("Архивная запись. Доступна для анализа, занимает минимум места.")
        lbl.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 11px; border: none;")
        self.content_layout.addWidget(lbl)

    def _clear_content(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
    def update_data(self, new_data):
        self.chunk_data = new_data
        self._update_appearance()

    def _on_delete(self):
        self.deleted.emit(self.chunk_id)


class AIMemoryPanel(QWidget):
    """
    Панель управления памятью ИИ.
    Показывает список чанков, позволяет обновлять память.
    """
    
    update_memory_requested = pyqtSignal()
    chunk_deleted = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.memory_manager = None
        self.chunk_manager = None
        self.cards = {} # chunk_id -> ChunkCard
        
        self._init_ui()
        
        # Таймер для обновления интерфейса (если что-то крутится)
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._refresh_active_chunks)
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.MD)
        
        # --- Header ---
        header = QFrame()
        header.setStyleSheet(Components.panel())
        header_layout = QHBoxLayout(header)
        # Важно: выравнивание контента в хедере по верху, чтобы не плавало
        header_layout.setAlignment(Qt.AlignmentFlag.AlignTop) 
        
        # Левая часть хедера (Заголовок + Иконка + Статистика)
        left_block = QVBoxLayout()
        left_block.setSpacing(4)
        left_block.setContentsMargins(0, 0, 0, 0)
        
        # Верхняя строка: Текст + Иконка
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_row.setContentsMargins(0, 0, 0, 0)
        # Принудительно прижимаем элементы влево
        top_row.setAlignment(Qt.AlignmentFlag.AlignLeft) 
        
        t_lbl = QLabel("Долговременная память ИИ")
        t_lbl.setStyleSheet(Components.section_title())
        t_lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred) # Не даем растягиваться
        top_row.addWidget(t_lbl)
        
        # Иконка информации
        self.info_icon = QLabel("ⓘ")
        self.info_icon.setCursor(Qt.CursorShape.PointingHandCursor)
        self.info_icon.setStyleSheet(f"""
            QLabel {{
                color: {Palette.PRIMARY};
                font-size: 18px;
                font-weight: bold;
                margin-top: 2px; /* Чуть опустить визуально */
            }}
            QLabel:hover {{
                color: {Palette.PRIMARY};
            }}
        """)
        
        # Текст тултипа (HTML для форматирования)
        tooltip_text = """
        <div style='width: 400px; font-family: sans-serif;'>
            <h3 style='color: #88C0D0;'>🧠 Как работает Память ИИ?</h3>
            <p>Эта система позволяет нейросети запоминать рыночные тренды, чтобы не анализировать каждый товар "с нуля".</p>
            <hr>
            <h4>1. Автоматическое обнаружение</h4>
            <p>Система сама сканирует вашу базу. Если вы спарсили много похожих товаров (например, >5 видеокарт), 
            она создает <b>Ячейку Памяти (Чанк)</b> со статусом ⏳ <i>В ожидании</i>.</p>
            
            <h4>2. Актуализация (Культивация)</h4>
            <p>Когда вы нажимаете <b>"Актуализировать память"</b>, ИИ анализирует всю группу товаров и пишет 
            аналитический отчет.</p>
            
            <h4>3. Использование при анализе</h4>
            <p>Когда вы анализируете новые объявления, ИИ сначала смотрит в Память. 
            Если он знает эту категорию, он сравнит цену товара с <b>рыночной статистикой (медианой и средней)</b>, 
            учитывая тренды и риски, сохраненные ранее.</p>
            <hr>
            <p style='color: #EBCB8B;'><i>💡 Совет: Обновляйте память раз в неделю, чтобы ИИ знал свежие цены.</i></p>
        </div>
        """
        self.info_icon.setToolTip(tooltip_text)
        self.info_icon.installEventFilter(self)
        
        top_row.addWidget(self.info_icon)
        left_block.addLayout(top_row)
        
        # Нижняя строка: Статистика
        self.stats_lbl = QLabel("Загрузка...")
        self.stats_lbl.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 12px;")
        left_block.addWidget(self.stats_lbl)
        
        header_layout.addLayout(left_block)
        header_layout.addStretch() # Толкаем все влево
        
        layout.addWidget(header)
        
        # --- Scroll Area ---
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(Components.scroll_area())
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setSpacing(10)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.addStretch()
        
        self.scroll.setWidget(self.cards_container)
        layout.addWidget(self.scroll)
        
        # --- Footer ---
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        
        self.btn_update = QPushButton("Актуализировать память")
        self.btn_update.setStyleSheet(Components.start_button())
        self.btn_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_update.clicked.connect(self._on_update_clicked)
        
        footer_layout.addWidget(self.btn_update)
        layout.addLayout(footer_layout)

    def eventFilter(self, obj, event):
        if obj == self.info_icon and event.type() == QEvent.Type.ToolTip:
            # -1 означает, что тултип не исчезнет, пока курсор не уйдет
            QToolTip.showText(event.globalPos(), obj.toolTip(), obj, obj.rect(), -1)
            return True
        return super().eventFilter(obj, event)

    def set_managers(self, memory_manager, chunk_manager):
        self.memory_manager = memory_manager
        self.chunk_manager = chunk_manager
        
        # Подписка на сигналы менеджера
        if self.chunk_manager:
            self.chunk_manager.chunk_status_changed.connect(self._on_chunk_status_changed)
            self.chunk_manager.cultivation_ready.connect(self._on_cultivation_ready)
            
        self._load_all_chunks()

    def _load_all_chunks(self):
        if not self.memory_manager: return
        
        # Очистка
        for cid, card in list(self.cards.items()):
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self.cards.clear()
        
        # Загрузка
        chunks = self.memory_manager.get_all_chunks()
        
        # Сортировка: сначала INITIALIZING, потом PENDING, потом новые READY
        # (SQL уже сортирует по date desc, но статусы важнее)
        def sort_key(c):
            s = c.get('status')
            if s == 'INITIALIZING': return 0
            if s == 'PENDING': return 1
            return 2
            
        chunks.sort(key=sort_key)
        
        # Удаляем стретч в конце перед добавлением (мы его добавим обратно в конце списка)
        # Hacky way to keep items at top
        item = self.cards_layout.takeAt(self.cards_layout.count() - 1)
        if item.widget(): item.widget().deleteLater()
        
        for chunk in chunks:
            self._add_card(chunk)
            
        self.cards_layout.addStretch()
        self._update_stats()

    def _add_card(self, chunk_data):
        card = ChunkCard(chunk_data)
        card.deleted.connect(self._on_card_deleted)
        self.cards[chunk_data['id']] = card
        # Добавляем в начало (перед stretch, который мы пока убрали, но если используем insertWidget 0...)
        # Проще вставлять в конец списка перед stretch
        self.cards_layout.insertWidget(self.cards_layout.count(), card)

    def _on_card_deleted(self, chunk_id):
        if self.memory_manager:
            self.memory_manager.delete_chunk(chunk_id)
            
        if chunk_id in self.cards:
            card = self.cards.pop(chunk_id)
            card.deleteLater()
            
        self._update_stats()
        self.chunk_deleted.emit(chunk_id)

    def _on_update_clicked(self):
        self.btn_update.setEnabled(False)
        self.btn_update.setText("Запуск процессов...")
        self.update_memory_requested.emit()
        
        # Визуальный отклик
        QTimer.singleShot(2000, lambda: self.btn_update.setText("⚡ Актуализировать память"))
        QTimer.singleShot(2000, lambda: self.btn_update.setEnabled(True))

    def _on_chunk_status_changed(self, chunk_id, new_status):
        if chunk_id in self.cards:
            # Обновляем существующую
            data = self.memory_manager.get_chunk_by_id(chunk_id)
            if data:
                self.cards[chunk_id].update_data(data)
        else:
            # Возможно это новый чанк
            data = self.memory_manager.get_chunk_by_id(chunk_id)
            if data:
                # Нужно вставить аккуратно, удалив stretch и вернув
                # Для простоты:
                self.cards_layout.takeAt(self.cards_layout.count() - 1) # remove stretch
                self._add_card(data)
                self.cards_layout.addStretch()
        
        self._update_stats()
        
        # Если что-то формируется, можно включить таймер для обновления прогресс баров
        # (в данной реализации они обновляются через сигнал, но таймер надежнее для UI)
        if new_status == 'INITIALIZING':
            if not self.refresh_timer.isActive():
                self.refresh_timer.start(1000)

    def _on_cultivation_ready(self, chunk_id):
        if chunk_id in self.cards:
            data = self.memory_manager.get_chunk_by_id(chunk_id)
            if data:
                self.cards[chunk_id].update_data(data)
        self._update_stats()

    def _refresh_active_chunks(self):
        # Проверяем, есть ли активные процессы
        active = False
        for cid, card in self.cards.items():
            if card.status == 'INITIALIZING':
                active = True
                # Можно перечитать прогресс из БД
                data = self.memory_manager.get_chunk_by_id(cid)
                if data:
                    card.update_data(data)
        
        if not active:
            self.refresh_timer.stop()
            
    def _update_stats(self):
        total = len(self.cards)
        ready = sum(1 for c in self.cards.values() if c.status in ['READY', 'COMPRESSED'])
        compressed = sum(1 for c in self.cards.values() if c.status == 'COMPRESSED')
        
        self.stats_lbl.setText(f"Всего чанков: {total} | Готово: {ready} | Сжато: {compressed}")