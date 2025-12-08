from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QSpinBox, QCheckBox, QComboBox,
    QGroupBox, QLineEdit, QFileDialog, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal
from app.ui.styles import Components, Palette, Typography, Spacing
from app.config import AI_CTX_SIZE, AI_GPU_LAYERS, MODELS_DIR, DEFAULT_MODEL_NAME
import os

class SettingsDialog(QDialog):
    settings_changed = pyqtSignal(dict)
    model_downloaded = pyqtSignal(str)
    
    def __init__(self, current_settings: dict, parent=None):
        super().__init__(parent)
        self.current_settings = current_settings.copy()
        self.model_downloader = None  # Будет создан при необходимости
        
        self.setWindowTitle("Настройки")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setStyleSheet(Components.dialog())
        self._init_ui()
        self._load_settings()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(Spacing.LG)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        
        layout.addWidget(self._create_model_download_section())
        layout.addWidget(self._create_parser_settings())
        layout.addWidget(self._create_ai_settings())
        layout.addWidget(self._create_debug_settings())
        
        layout.addStretch()
        layout.addLayout(self._create_buttons())
    
    def _create_model_download_section(self) -> QGroupBox:
        group = self._create_group("Скачивание модели")
        layout = QVBoxLayout()
        layout.setSpacing(Spacing.SM)
        
        # Описание
        info_label = QLabel(
            "Стандартная модель для работы ИИ-функций:\n"
            f"📦 {DEFAULT_MODEL_NAME} (~4.1 ГБ)"
        )
        info_label.setStyleSheet(f"color: {Palette.TEXT_SECONDARY};")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        download_row = QHBoxLayout()
        
        self.btn_download_model = QPushButton("📥 Скачать стандартную модель")
        self.btn_download_model.setStyleSheet(Components.start_button())
        self.btn_download_model.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_download_model.clicked.connect(self._on_download_model)
        download_row.addWidget(self.btn_download_model)
        
        self.btn_cancel_download = QPushButton("✖ Отменить")
        self.btn_cancel_download.setStyleSheet(Components.stop_button())
        self.btn_cancel_download.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel_download.clicked.connect(self._on_cancel_download)
        self.btn_cancel_download.setVisible(False)
        download_row.addWidget(self.btn_cancel_download)
        
        layout.addLayout(download_row)
        
        self.download_progress = QProgressBar()
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(0)
        self.download_progress.setTextVisible(True)
        self.download_progress.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: {Spacing.RADIUS_NORMAL}px;
                background-color: {Palette.BG_DARK_2};
                text-align: center;
                color: {Palette.TEXT};
                min-height: 25px;
            }}
            QProgressBar::chunk {{
                background-color: {Palette.SUCCESS};
                border-radius: {Spacing.RADIUS_NORMAL - 1}px;
            }}
        """)
        self.download_progress.setVisible(False)
        layout.addWidget(self.download_progress)
        
        self.download_status = QLabel("")
        self.download_status.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: {Typography.SIZE_SMALL}px;")
        self.download_status.setVisible(False)
        layout.addWidget(self.download_status)
        
        group.setLayout(layout)
        return group

    def _on_download_model(self):
        from app.core.model_downloader import ModelDownloader
        
        if not self.model_downloader:
            self.model_downloader = ModelDownloader()
            self.model_downloader.progress_updated.connect(self._on_download_progress)
            self.model_downloader.download_finished.connect(self._on_download_finished)
            self.model_downloader.download_failed.connect(self._on_download_failed)
            self.model_downloader.download_cancelled.connect(self._on_download_cancelled)
        
        target_path = os.path.join(MODELS_DIR, DEFAULT_MODEL_NAME)
        if os.path.exists(target_path) and os.path.getsize(target_path) > 1024:
            from PyQt6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self,
                "Модель существует",
                f"Модель {DEFAULT_MODEL_NAME} уже скачана.\n\nСкачать заново?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
            
            try:
                os.remove(target_path)
            except:
                pass
        
        self.btn_download_model.setEnabled(False)
        self.btn_cancel_download.setVisible(True)
        self.download_progress.setVisible(True)
        self.download_progress.setValue(0)
        self.download_status.setVisible(True)
        self.download_status.setText("Подготовка к скачиванию...")
        
        self.model_downloader.start_download()

    def _on_cancel_download(self):
        if self.model_downloader:
            self.model_downloader.cancel_download()

    def _on_download_progress(self, percent: int, downloaded_mb: float, total_mb: float, speed_str: str):
        self.download_progress.setValue(percent)
        self.download_progress.setFormat(f"{percent}% ({downloaded_mb:.1f} / {total_mb:.1f} MB)")
        self.download_status.setText(speed_str)
    
    def _on_download_finished(self, file_path: str):
        self.download_progress.setValue(100)
        self.download_status.setText("Скачивание завершено успешно!")
        self.download_status.setStyleSheet(f"color: {Palette.SUCCESS}; font-size: {Typography.SIZE_SMALL}px;")
        
        self.btn_cancel_download.setVisible(False)
        self.btn_download_model.setEnabled(True)
        self.btn_download_model.setText("✅ Модель загружена")
        
        self._populate_models()
        
        idx = self.model_combo.findText(DEFAULT_MODEL_NAME)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        
        self.model_downloaded.emit(file_path)
    
    def _on_download_failed(self, error_msg: str):
        from PyQt6.QtWidgets import QMessageBox
        
        self.download_status.setText(f"Ошибка: {error_msg}")
        self.download_status.setStyleSheet(f"color: {Palette.ERROR}; font-size: {Typography.SIZE_SMALL}px;")
        
        self.btn_cancel_download.setVisible(False)
        self.btn_download_model.setEnabled(True)
        
        QMessageBox.critical(
            self,
            "Ошибка скачивания",
            f"Не удалось скачать модель:\n\n{error_msg}",
            QMessageBox.StandardButton.Ok
        )
    
    def _on_download_cancelled(self):
        self.download_progress.setValue(0)
        self.download_status.setText("Скачивание отменено")
        self.download_status.setStyleSheet(f"color: {Palette.WARNING}; font-size: {Typography.SIZE_SMALL}px;")
        
        self.btn_cancel_download.setVisible(False)
        self.btn_download_model.setEnabled(True)

    def _create_group(self, title):
        group = QGroupBox(title)
        group.setStyleSheet(f"""
            QGroupBox {{
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: {Spacing.RADIUS_NORMAL}px;
                margin-top: {Spacing.MD}px;
                padding-top: {Spacing.MD}px;
                font-weight: bold;
                color: {Palette.TEXT_SECONDARY};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: {Spacing.SM}px; padding: 0 {Spacing.XS}px;
            }}
        """)
        return group

    def _create_parser_settings(self) -> QGroupBox:
        group = self._create_group("Парсер")
        layout = QVBoxLayout()
        layout.setSpacing(Spacing.SM)
        
        self.request_delay_spin = self._add_spin_row(layout, "Задержка между запросами (мс):", 100, 5000, 500)
        self.max_retries_spin = self._add_spin_row(layout, "Максимум повторов при ошибке:", 1, 10, 3)
        self.page_timeout_spin = self._add_spin_row(layout, "Таймаут загрузки страницы (сек):", 5, 60, 15)
        self.fav_monitor_spin = self._add_spin_row(layout, "Интервал мониторинга (мин):", 1, 1440, 15)

        group.setLayout(layout)
        return group
    
    def _add_spin_row(self, layout, label, min_v, max_v, default):
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        spin = QSpinBox()
        spin.setRange(min_v, max_v)
        spin.setValue(default)
        spin.setStyleSheet(Components.text_input())
        row.addWidget(spin)
        row.addStretch()
        layout.addLayout(row)
        return spin

    def _create_ai_settings(self) -> QGroupBox:
        group = self._create_group("Нейросеть")
        layout = QVBoxLayout()
        layout.setSpacing(Spacing.SM)
        
        row = QHBoxLayout()
        row.addWidget(QLabel("Модель:"))
        self.model_combo = QComboBox()
        self.model_combo.setStyleSheet(Components.text_input()) # Combo shares style
        self._populate_models()
        row.addWidget(self.model_combo, 1)
        btn_refresh = QPushButton("🔄")
        btn_refresh.setFixedWidth(30)
        btn_refresh.setStyleSheet(Components.small_button())
        btn_refresh.clicked.connect(self._populate_models)
        row.addWidget(btn_refresh)
        layout.addLayout(row)
        
        self.ctx_size_spin = self._add_spin_row(layout, "Размер контекста:", 512, 32768, AI_CTX_SIZE)
        self.ctx_size_spin.setSingleStep(512)
        self.gpu_layers_spin = self._add_spin_row(layout, "GPU слои (-1 = все):", -1, 100, AI_GPU_LAYERS or -1)
        
        brow = QHBoxLayout()
        brow.addWidget(QLabel("Бэкенд:"))
        self.backend_combo = QComboBox()
        self.backend_combo.addItems(["auto", "cuda", "cpu", "vulkan"])
        self.backend_combo.setStyleSheet(Components.text_input())
        brow.addWidget(self.backend_combo)
        brow.addStretch()
        layout.addLayout(brow)
        
        group.setLayout(layout)
        return group
    
    def _create_debug_settings(self) -> QGroupBox:
        group = self._create_group("Отладка")
        layout = QVBoxLayout()
        self.debug_mode_check = QCheckBox("Режим отладки (подробные логи)")
        self.ai_debug_check = QCheckBox("Отладка AI (логи в debug_ai.log)")
        self.parser_debug_check = QCheckBox("Отладка парсера (детали)")
        for chk in [self.debug_mode_check, self.ai_debug_check, self.parser_debug_check]:
            chk.setStyleSheet(f"color: {Palette.TEXT};")
            layout.addWidget(chk)
        group.setLayout(layout)
        return group
    
    def _create_buttons(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.addStretch()
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        btn_cancel.setStyleSheet(Components.stop_button())
        layout.addWidget(btn_cancel)
        btn_apply = QPushButton("Применить")
        btn_apply.setStyleSheet(Components.start_button())
        btn_apply.clicked.connect(self._on_apply)
        layout.addWidget(btn_apply)
        return layout
    
    def _populate_models(self):
        self.model_combo.clear()
        if not os.path.exists(MODELS_DIR):
            self.model_combo.addItem("(нет моделей)")
            return
        models = [f for f in os.listdir(MODELS_DIR) if f.endswith('.gguf')]
        if not models: self.model_combo.addItem("(нет моделей)")
        else:
            for model in sorted(models): self.model_combo.addItem(model)
    
    def _load_settings(self):
        self.request_delay_spin.setValue(self.current_settings.get("request_delay", 500))
        self.max_retries_spin.setValue(self.current_settings.get("max_retries", 3))
        self.page_timeout_spin.setValue(self.current_settings.get("page_timeout", 15))
        self.ctx_size_spin.setValue(self.current_settings.get("ai_ctx_size", AI_CTX_SIZE))
        self.gpu_layers_spin.setValue(self.current_settings.get("ai_gpu_layers", -1))
        backend = self.current_settings.get("ai_backend", "auto")
        idx = self.backend_combo.findText(backend)
        if idx >= 0: self.backend_combo.setCurrentIndex(idx)
        self.debug_mode_check.setChecked(self.current_settings.get("debug_mode", False))
        self.ai_debug_check.setChecked(self.current_settings.get("ai_debug", False))
        self.parser_debug_check.setChecked(self.current_settings.get("parser_debug", False))
        self.fav_monitor_spin.setValue(self.current_settings.get("favorites_monitor_interval", 15))
        model = self.current_settings.get("ai_model", "")
        if model:
            idx = self.model_combo.findText(model)
            if idx >= 0: self.model_combo.setCurrentIndex(idx)
    
    def _on_apply(self):
        settings = {
            "request_delay": self.request_delay_spin.value(),
            "max_retries": self.max_retries_spin.value(),
            "page_timeout": self.page_timeout_spin.value(),
            "ai_ctx_size": self.ctx_size_spin.value(),
            "ai_gpu_layers": self.gpu_layers_spin.value(),
            "ai_backend": self.backend_combo.currentText(),
            "ai_model": self.model_combo.currentText(),
            "debug_mode": self.debug_mode_check.isChecked(),
            "ai_debug": self.ai_debug_check.isChecked(),
            "parser_debug": self.parser_debug_check.isChecked(),
            "favorites_monitor_interval": self.fav_monitor_spin.value(),
        }
        self.settings_changed.emit(settings)
        self.accept()
    
    def get_settings(self) -> dict: return self.current_settings # (updated via apply)