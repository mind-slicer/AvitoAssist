from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy, QGridLayout
from PyQt6.QtCore import Qt
from app.ui.styles import Palette, Typography, Components, Spacing

class AIStatsPanel(QWidget):
    """
    Переделанная панель статистики AI с GridLayout.
    Структура: Иконка | Название | Значение
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AIStatsPanel")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        
        main = QVBoxLayout(self)
        main.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        main.setSpacing(Spacing.SM)

        # Заголовок
        title_ai = QLabel("СТАТУС ИИ")
        title_ai.setStyleSheet(Components.section_title())
        main.addWidget(title_ai)
        
        # GridLayout для элементов (Иконка | Название | Значение)
        grid = QGridLayout()
        grid.setColumnStretch(0, 0)  # Иконка (минимум)
        grid.setColumnStretch(1, 0)  # Название (минимум)
        grid.setColumnStretch(2, 1)  # Значение (расширяется)
        grid.setSpacing(Spacing.SM)
        grid.setContentsMargins(0, 0, 0, 0)
        
        # Строка 0: Model
        icon_model = QLabel("🧠")
        icon_model.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_model = QLabel("Модель:")
        name_model.setStyleSheet(Typography.style(
            family=Typography.UI, 
            size=Typography.SIZE_MD, 
            weight=Typography.WEIGHT_SEMIBOLD,
            color=Palette.TEXT_MUTED
        ))
        self.lbl_model_name = QLabel("—")
        self.lbl_model_name.setStyleSheet(Typography.style(
            family=Typography.MONO, 
            size=Typography.SIZE_MD, 
            color=Palette.TEXT
        ))
        grid.addWidget(icon_model, 0, 0)
        grid.addWidget(name_model, 0, 1)
        grid.addWidget(self.lbl_model_name, 0, 2)
        
        # Строка 1: Memory
        icon_mem = QLabel("💾")
        icon_mem.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_mem = QLabel("VRAM | RAM:")
        name_mem.setStyleSheet(Typography.style(
            family=Typography.UI, 
            size=Typography.SIZE_MD, 
            weight=Typography.WEIGHT_SEMIBOLD,
            color=Palette.TEXT_MUTED
        ))
        self.lbl_memory = QLabel("—")
        self.lbl_memory.setStyleSheet(Typography.style(
            family=Typography.MONO, 
            size=Typography.SIZE_MD, 
            color=Palette.TEXT
        ))
        grid.addWidget(icon_mem, 1, 0)
        grid.addWidget(name_mem, 1, 1)
        grid.addWidget(self.lbl_memory, 1, 2)
        
        # Строка 2: Load
        icon_load = QLabel("⚡")
        icon_load.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_load = QLabel("Нагрузка:")
        name_load.setStyleSheet(Typography.style(
            family=Typography.UI, 
            size=Typography.SIZE_MD, 
            weight=Typography.WEIGHT_SEMIBOLD,
            color=Palette.TEXT_MUTED
        ))
        self.lbl_load = QLabel("—")
        self.lbl_load.setStyleSheet(Typography.style(
            family=Typography.MONO, 
            size=Typography.SIZE_MD, 
            color=Palette.TEXT
        ))
        grid.addWidget(icon_load, 2, 0)
        grid.addWidget(name_load, 2, 1)
        grid.addWidget(self.lbl_load, 2, 2)
        
        # Строка 3: Parser ETA
        icon_parser = QLabel("⏱️")
        icon_parser.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_parser = QLabel("Поиск:")
        name_parser.setStyleSheet(Typography.style(
            family=Typography.UI, 
            size=Typography.SIZE_MD, 
            weight=Typography.WEIGHT_SEMIBOLD,
            color=Palette.TEXT_MUTED
        ))
        self.lbl_parser_eta = QLabel("—")
        self.lbl_parser_eta.setStyleSheet(Typography.style(
            family=Typography.MONO, 
            size=Typography.SIZE_MD, 
            color=Palette.INFO
        ))
        grid.addWidget(icon_parser, 3, 0)
        grid.addWidget(name_parser, 3, 1)
        grid.addWidget(self.lbl_parser_eta, 3, 2)
        
        # Строка 4: AI ETA
        icon_ai = QLabel("🤖")
        icon_ai.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_ai = QLabel("Анализ:")
        name_ai.setStyleSheet(Typography.style(
            family=Typography.UI, 
            size=Typography.SIZE_MD, 
            weight=Typography.WEIGHT_SEMIBOLD,
            color=Palette.TEXT_MUTED
        ))
        self.lbl_ai_eta = QLabel("—")
        self.lbl_ai_eta.setStyleSheet(Typography.style(
            family=Typography.MONO, 
            size=Typography.SIZE_MD, 
            color=Palette.WARNING
        ))
        grid.addWidget(icon_ai, 4, 0)
        grid.addWidget(name_ai, 4, 1)
        grid.addWidget(self.lbl_ai_eta, 4, 2)
        
        main.addLayout(grid)
        
        self.setStyleSheet(Components.panel())
    
    def _format_duration(self, sec: float) -> str:
        """Форматирование времени в читаемый вид"""
        if not sec or sec <= 0:
            return "—"
        if sec < 60:
            return f"{int(sec)} с"
        m = int(sec // 60)
        h = m // 60
        m = m % 60
        if h > 0:
            return f"{h} ч {m} мин"
        return f"{m} мин"
    
    def update_stats(self, stats: dict):
        """Обновить статистику из словаря"""
        model_name = stats.get("model_name", "—")
        vram_mb = stats.get("vram_mb", 0.0)
        ram_mb = stats.get("ram_mb", 0.0)
        cpu = stats.get("cpu_percent", 0.0)
        gpu = stats.get("gpu_percent", 0.0)
        
        # Модель
        short_model = model_name[:20] + "..." if len(model_name) > 23 else model_name
        self.lbl_model_name.setText(short_model)
        
        # Память
        mem_text = f"{vram_mb:.0f} MB" if vram_mb > 0 else f"{ram_mb:.0f} MB"
        self.lbl_memory.setText(mem_text)
        
        # Нагрузка
        load_text = f"GPU {gpu:.0f}%" if gpu > 0 else f"CPU {cpu:.0f}%"
        self.lbl_load.setText(load_text)
        
        # ETA
        parser_eta = self._format_duration(stats.get('parser_eta_sec', 0.0))
        self.lbl_parser_eta.setText(parser_eta)
        
        ai_eta = self._format_duration(stats.get('ai_eta_sec', 0.0))
        self.lbl_ai_eta.setText(ai_eta)