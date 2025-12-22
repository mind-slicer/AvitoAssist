from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QProgressBar)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor
from app.ui.styles import Components, Palette, Typography, Spacing

class RAGStatusWidget(QWidget):
    rebuild_requested = pyqtSignal()
    
    def __init__(self, memory_manager, parent=None):
        super().__init__(parent)
        self.memory = memory_manager
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.MD)
        
        # Заголовок + статус
        header_layout = QHBoxLayout()
        
        title = QLabel("📊 Статус RAG-системы")
        title.setStyleSheet(Components.section_title())
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # Статус
        self.status_label = QLabel("Загрузка...")
        self.status_label.setStyleSheet(Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_MD,
            color=Palette.TEXT_MUTED
        ))
        header_layout.addWidget(self.status_label)
        
        self.btn_rebuild = QPushButton("🔄 Пересчитать статистику")
        self.btn_rebuild.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_rebuild.setStyleSheet(Components.small_button())
        self.btn_rebuild.clicked.connect(self.on_rebuild_clicked)
        header_layout.addWidget(self.btn_rebuild)
        
        layout.addLayout(header_layout)
        
        # Прогресс-бар (скрыт по умолчанию)
        self.progress = QProgressBar()
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: {Spacing.RADIUS_SMOOTH}px;
                background-color: {Palette.BG_DARK_3};
                text-align: center;
                height: 20px;
            }}
            QProgressBar::chunk {{
                background-color: {Palette.SECONDARY};
                border-radius: {Spacing.RADIUS_SMOOTH}px;
            }}
        """)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        
        # Таблица агрегатов
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Категория", "Средняя цена", "Медиана", "Мин", "Макс", "Тренд", "Товаров"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet(Components.table())
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)
        
        # Инфо внизу
        self.info_label = QLabel("Данные загружаются...")
        self.info_label.setStyleSheet(Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_SM,
            color=Palette.TEXT_MUTED
        ))
        layout.addWidget(self.info_label)

        self.detail_label = QLabel("Кликните по категории, чтобы посмотреть сводку.")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet(Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_SM,
            color=Palette.TEXT
        ))
        layout.addWidget(self.detail_label)

        self.table.cellClicked.connect(self.on_row_clicked)

    def on_row_clicked(self, row: int, col: int):
        item = self.table.item(row, 0)
        if not item:
            return
        product_key = item.text().strip()
        if not product_key:
            return
    
        ctx = self.memory.get_rag_context_for_product_key(product_key)
        if not ctx:
            self.detail_label.setText("Нет подробной статистики для этой категории.")
            return
    
        trend_map = {
            "up": "цены растут",
            "down": "цены падают",
            "stable": "цены стабилизировались"
        }
        trend_txt = trend_map.get(ctx["trend"], "нет данных по тренду")
        tp = ctx.get("trend_percent", 0.0)
    
        text = (
            f"Категория: {product_key}\n"
            f"Средняя цена: {ctx['avg_price']} ₽, медиана: {ctx['median_price']} ₽\n"
            f"Диапазон: {ctx['min_price']}–{ctx['max_price']} ₽, всего товаров: {ctx['sample_count']}\n"
            f"Тренд: {trend_txt} ({tp:+.1f}%)."
        )
        self.detail_label.setText(text)

    def refresh_data(self):
        """Обновить данные в таблице"""
        stats = self.memory.get_all_statistics(limit=200)
        status = self.memory.get_rag_status()
        
        if self.table.rowCount() > 0:
            self.on_row_clicked(0, 0)
        else:
            self.detail_label.setText("")

        # Обновляем статус
        status_map = {
            'ok': '✅ Актуально',
            'outdated': '⚠️ Требует обновления',
            'empty': '❌ Пусто'
        }
        status_text = status_map.get(status['status'], '—')
        self.status_label.setText(status_text)
        
        # Обновляем инфо
        last_upd = status['last_rebuild']
        if last_upd and last_upd != 'Never':
            try:
                from datetime import datetime
                dt = datetime.strptime(last_upd, "%Y-%m-%d %H:%M:%S")
                formatted = dt.strftime("%d.%m.%Y %H:%M")
            except:
                formatted = last_upd
            self.info_label.setText(f"Последнее обновление: {formatted} | Товаров: {status['total_items']} | Категорий: {status['total_categories']}")
        else:
            self.info_label.setText(f"Товаров: {status['total_items']} | Категорий: {status['total_categories']} | Обновление не выполнялось")
        
        # Заполняем таблицу
        self.table.setRowCount(len(stats))
        for r, stat in enumerate(stats):
            # Категория
            self.table.setItem(r, 0, QTableWidgetItem(stat.get('product_key', '')))
            
            # Средняя цена
            avg = stat.get('avg_price', 0)
            self.table.setItem(r, 1, QTableWidgetItem(f"{avg:,}".replace(',', ' ')))
            
            # Медиана
            med = stat.get('median_price', 0)
            self.table.setItem(r, 2, QTableWidgetItem(f"{med:,}".replace(',', ' ')))
            
            # Мин
            min_p = stat.get('min_price', 0)
            self.table.setItem(r, 3, QTableWidgetItem(f"{min_p:,}".replace(',', ' ')))
            
            # Макс
            max_p = stat.get('max_price', 0)
            self.table.setItem(r, 4, QTableWidgetItem(f"{max_p:,}".replace(',', ' ')))
            
            # Тренд
            trend = stat.get('trend', 'stable')
            trend_percent = stat.get('trend_percent', 0.0)
            trend_icons = {'up': '📈', 'down': '📉', 'stable': '➡️'}
            trend_text = f"{trend_icons.get(trend, '—')} {trend_percent:+.1f}%"
            trend_item = QTableWidgetItem(trend_text)
            
            # Цвет тренда
            if trend == 'up':
                trend_item.setForeground(QColor(Palette.WARNING))
            elif trend == 'down':
                trend_item.setForeground(QColor(Palette.SUCCESS))
            else:
                trend_item.setForeground(QColor(Palette.TEXT_MUTED))
            
            trend_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 5, trend_item)
            
            # Товаров
            count = stat.get('sample_count', 0)
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 6, count_item)
    
    def on_rebuild_clicked(self):
        """Запуск пересчета"""
        self.btn_rebuild.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # Бесконечный прогресс
        self.status_label.setText("🔄 Пересчитываю...")
        
        self.rebuild_requested.emit()
        
        # Через 3 секунды разблокируем кнопку и обновим данные
        QTimer.singleShot(3000, self.finish_rebuild)
    
    def finish_rebuild(self):
        """Завершение пересчета"""
        self.progress.setVisible(False)
        self.btn_rebuild.setEnabled(True)
        QTimer.singleShot(500, self.refresh_data)