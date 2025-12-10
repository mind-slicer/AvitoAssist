import os
import shutil
import requests
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QSpinBox, QCheckBox, QComboBox,
    QGroupBox, QLineEdit, QProgressBar, QMessageBox, QTabWidget, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
from app.ui.styles import Components, Palette, Typography, Spacing
from app.config import AI_CTX_SIZE, AI_GPU_LAYERS, MODELS_DIR, DEFAULT_MODEL_NAME, BASE_APP_DIR

class SettingsDialog(QDialog):
    settings_changed = pyqtSignal(dict)
    model_downloaded = pyqtSignal(str)
    factory_reset_requested = pyqtSignal()
    
    def __init__(self, current_settings: dict, parent=None):
        super().__init__(parent)
        self.current_settings = current_settings.copy()
        self.model_downloader = None
        
        self.setWindowTitle("Настройки")
        self.setModal(True)
        self.resize(700, 650)
        self.setStyleSheet(Components.dialog())
        self._init_ui()
        self._load_settings()
    
    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        main_layout.setSpacing(Spacing.MD)

        # Используем табы для разделения настроек
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid {Palette.BORDER_SOFT}; border-radius: {Spacing.RADIUS_NORMAL}px; }}
            QTabBar::tab {{
                background: {Palette.BG_DARK_2};
                color: {Palette.TEXT_MUTED};
                padding: 8px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{ background: {Palette.BG_LIGHT}; color: {Palette.PRIMARY}; }}
        """)

        # Таб 1: Основные (Парсер + AI)
        tab_general = QWidget()
        layout_general = QVBoxLayout(tab_general)
        layout_general.setSpacing(Spacing.MD)
        layout_general.addWidget(self._create_parser_settings())
        layout_general.addWidget(self._create_ai_settings())
        layout_general.addWidget(self._create_model_download_section())
        layout_general.addStretch()
        self.tabs.addTab(tab_general, "Основные")

        # Таб 2: Уведомления (Telegram)
        tab_notify = QWidget()
        layout_notify = QVBoxLayout(tab_notify)
        layout_notify.setSpacing(Spacing.MD)
        layout_notify.addWidget(self._create_telegram_settings())
        layout_notify.addStretch()
        self.tabs.addTab(tab_notify, "Уведомления")

        # Таб 3: Система (Отладка + Сброс)
        tab_system = QWidget()
        layout_system = QVBoxLayout(tab_system)
        layout_system.setSpacing(Spacing.MD)
        layout_system.addWidget(self._create_debug_settings())
        layout_system.addWidget(self._create_danger_zone())
        layout_system.addStretch()
        self.tabs.addTab(tab_system, "Система")

        main_layout.addWidget(self.tabs)
        main_layout.addLayout(self._create_buttons())
    
    # --- TELEGRAM SETTINGS ---
    def _create_telegram_settings(self) -> QGroupBox:
        group = self._create_group("Telegram Бот")
        layout = QVBoxLayout()
        layout.setSpacing(Spacing.MD)

        # Инструкция
        info = QLabel(
            "1. Создайте бота через @BotFather и получите Token.\n"
            "2. Узнайте свой Chat ID через @userinfobot.\n"
            "3. Бот будет присылать уведомления о новых избранных товарах и изменении цены."
        )
        info.setStyleSheet(f"color: {Palette.TEXT_SECONDARY}; font-size: 13px;")
        layout.addWidget(info)

        # Поля ввода
        self.tg_token_input = QLineEdit()
        self.tg_token_input.setPlaceholderText("Например: 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
        self.tg_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.tg_token_input.setStyleSheet(Components.text_input())
        
        self.tg_chat_id_input = QLineEdit()
        self.tg_chat_id_input.setPlaceholderText("Например: 123456789")
        self.tg_chat_id_input.setStyleSheet(Components.text_input())

        layout.addLayout(self._create_input_row("Bot Token:", self.tg_token_input))
        layout.addLayout(self._create_input_row("Chat ID:", self.tg_chat_id_input))

        # Настройки трекера
        self.tg_interval_spin = QSpinBox()
        self.tg_interval_spin.setRange(5, 1440)
        self.tg_interval_spin.setValue(60)
        self.tg_interval_spin.setSuffix(" мин")
        self.tg_interval_spin.setStyleSheet(Components.text_input())
        layout.addLayout(self._create_input_row("Интервал проверки избранного:", self.tg_interval_spin))

        # Кнопка теста
        self.btn_test_tg = QPushButton("📨 Проверить подключение")
        self.btn_test_tg.setStyleSheet(Components.small_button())
        self.btn_test_tg.clicked.connect(self._test_telegram)
        layout.addWidget(self.btn_test_tg)

        group.setLayout(layout)
        return group

    def _create_input_row(self, label_text, widget):
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setMinimumWidth(120)
        lbl.setStyleSheet(f"color: {Palette.TEXT};")
        row.addWidget(lbl)
        row.addWidget(widget)
        return row

    def _test_telegram(self):
        token = self.tg_token_input.text().strip()
        chat_id = self.tg_chat_id_input.text().strip()
        
        if not token or not chat_id:
            QMessageBox.warning(self, "Ошибка", "Введите Token и Chat ID")
            return
            
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            resp = requests.post(url, json={"chat_id": chat_id, "text": "🤖 Avito Assist: Тестовое сообщение!"}, timeout=5)
            if resp.status_code == 200:
                QMessageBox.information(self, "Успех", "Сообщение отправлено! Проверьте Telegram.")
            else:
                QMessageBox.error(self, "Ошибка API", f"Код ответа: {resp.status_code}\n{resp.text}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сети", str(e))

    # --- DANGER ZONE ---
    def _create_danger_zone(self) -> QGroupBox:
        group = self._create_group("Сброс настроек")
        group.setStyleSheet(group.styleSheet() + f"QGroupBox {{ border-color: {Palette.ERROR}; }}")
        layout = QVBoxLayout()
        
        warn = QLabel("Внимание! Это действие удалит все настройки, пресеты тегов и базу знаний ИИ.\nСохраненные таблицы результатов (Excel/JSON) останутся.")
        warn.setWordWrap(True)
        warn.setStyleSheet(f"color: {Palette.ERROR}; font-weight: bold;")
        layout.addWidget(warn)

        btn_reset = QPushButton("☢ СБРОСИТЬ ВСЕ К ЗАВОДСКИМ НАСТРОЙКАМ")
        btn_reset.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_DARK_2};
                border: 1px solid {Palette.ERROR};
                color: {Palette.ERROR};
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {Palette.ERROR}; color: {Palette.TEXT}; }}
        """)
        btn_reset.clicked.connect(self._on_factory_reset)
        layout.addWidget(btn_reset)
        
        group.setLayout(layout)
        return group

    def _on_factory_reset(self):
        import sys
        import subprocess
        from PyQt6.QtWidgets import QApplication

        confirm = QMessageBox.warning(
            self, "Подтверждение сброса", 
            "Вы уверены? Приложение будет перезапущено как новое.\n"
            "Все ваши настройки, база знаний ИИ и история поиска будут удалены.\n\n"
            "Таблицы с результатами останутся нетронутыми.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if confirm == QMessageBox.StandardButton.Yes:
            # Список файлов на удаление
            files_to_remove = [
                "app_settings.json", 
                "queues_state.json", 
                "tag_presets.json",
                "tag_presets_ignore.json",
                "categories_cache.json",
                "avito_cookies.pkl",  # <--- Важно: сброс сессии браузера
                "debug.log"           # <--- Очистка логов
            ]
            
            # Удаляем папку data (база знаний)
            data_dir = os.path.join(BASE_APP_DIR, "data")
            
            try:
                # 1. Удаляем файлы
                for f in files_to_remove:
                    path = os.path.join(BASE_APP_DIR, f)
                    if os.path.exists(path):
                        try:
                            os.remove(path)
                        except Exception as e:
                            print(f"Не удалось удалить {f}: {e}")
                
                # 2. Удаляем папку
                if os.path.exists(data_dir):
                    shutil.rmtree(data_dir, ignore_errors=True)
                    
                # 3. Перезапуск приложения
                QMessageBox.information(self, "Перезагрузка", "Настройки сброшены. Приложение будет перезапущено.")
                
                # Получаем путь к текущему исполняемому файлу/скрипту
                if getattr(sys, 'frozen', False):
                    # Если скомпилировано в .exe
                    executable = sys.executable
                    args = []
                else:
                    # Если запуск через python script.py
                    executable = sys.executable
                    args = sys.argv
                
                # Запускаем новый процесс
                subprocess.Popen([executable] + args)
                
                # Завершаем текущий
                QApplication.quit()
                
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Сбой при сбросе настроек: {e}")

    # --- EXISTING METHODS (Shortened for brevity, logic preserved) ---
    def _create_model_download_section(self) -> QGroupBox:
        group = self._create_group("Скачивание модели")
        layout = QVBoxLayout()
        layout.setSpacing(Spacing.SM)
        
        info_label = QLabel(f"Стандартная модель: {DEFAULT_MODEL_NAME} (~4.1 ГБ)")
        info_label.setStyleSheet(f"color: {Palette.TEXT_SECONDARY};")
        layout.addWidget(info_label)
        
        download_row = QHBoxLayout()
        self.btn_download_model = QPushButton("📥 Скачать")
        self.btn_download_model.setStyleSheet(Components.start_button())
        self.btn_download_model.clicked.connect(self._on_download_model)
        download_row.addWidget(self.btn_download_model)
        
        self.btn_cancel_download = QPushButton("✖")
        self.btn_cancel_download.setStyleSheet(Components.stop_button())
        self.btn_cancel_download.clicked.connect(self._on_cancel_download)
        self.btn_cancel_download.setVisible(False)
        download_row.addWidget(self.btn_cancel_download)
        
        layout.addLayout(download_row)
        
        self.download_progress = QProgressBar()
        self.download_progress.setVisible(False)
        self.download_progress.setStyleSheet(f"QProgressBar {{ border: 1px solid {Palette.BORDER_SOFT}; background: {Palette.BG_DARK_2}; color: {Palette.TEXT}; text-align: center; }} QProgressBar::chunk {{ background: {Palette.SUCCESS}; }}")
        layout.addWidget(self.download_progress)
        
        self.download_status = QLabel("")
        self.download_status.setVisible(False)
        layout.addWidget(self.download_status)
        
        group.setLayout(layout)
        return group

    # ... (Download logic methods _on_download_model, etc. keep same as before) ...
    def _on_download_model(self):
        from app.core.model_downloader import ModelDownloader
        if not self.model_downloader:
            self.model_downloader = ModelDownloader()
            self.model_downloader.progress_updated.connect(self._on_download_progress)
            self.model_downloader.download_finished.connect(self._on_download_finished)
            self.model_downloader.download_failed.connect(self._on_download_failed)
        
        self.btn_download_model.setEnabled(False)
        self.btn_cancel_download.setVisible(True)
        self.download_progress.setVisible(True)
        self.download_status.setVisible(True)
        self.model_downloader.start_download()

    def _on_cancel_download(self):
        if self.model_downloader: self.model_downloader.cancel_download()
    
    def _on_download_progress(self, pct, d_mb, t_mb, speed):
        self.download_progress.setValue(pct)
        self.download_status.setText(f"{speed} | {d_mb:.1f}/{t_mb:.1f} MB")
    
    def _on_download_finished(self, path):
        self.download_progress.setValue(100)
        self.download_status.setText("Готово!")
        self.btn_cancel_download.setVisible(False)
        self.btn_download_model.setEnabled(True)
        self.btn_download_model.setText("✅ Скачано")
        self._populate_models()
        self.model_downloaded.emit(path)

    def _on_download_failed(self, msg):
        self.download_status.setText(f"Ошибка: {msg}")
        self.btn_cancel_download.setVisible(False)
        self.btn_download_model.setEnabled(True)

    def _create_group(self, title):
        group = QGroupBox(title)
        group.setStyleSheet(f"QGroupBox {{ border: 1px solid {Palette.BORDER_SOFT}; border-radius: 5px; margin-top: 10px; padding-top: 10px; color: {Palette.TEXT_SECONDARY}; font-weight: bold; }} QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; }}")
        return group

    def _create_parser_settings(self) -> QGroupBox:
        group = self._create_group("Настройки парсера")
        layout = QVBoxLayout()
        self.request_delay_spin = self._add_spin_row(layout, "Задержка (мс):", 100, 5000, 500)
        self.max_retries_spin = self._add_spin_row(layout, "Повторы:", 1, 10, 3)
        self.page_timeout_spin = self._add_spin_row(layout, "Таймаут (сек):", 5, 60, 15)
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
        layout.addLayout(row)
        return spin

    def _create_ai_settings(self) -> QGroupBox:
        group = self._create_group("Параметры ИИ")
        layout = QVBoxLayout()
        
        self.model_combo = QComboBox()
        self.model_combo.setStyleSheet(Components.text_input())
        self._populate_models()
        layout.addWidget(QLabel("Модель:"))
        layout.addWidget(self.model_combo)
        
        self.ctx_size_spin = self._add_spin_row(layout, "Контекст (токенов):", 512, 32768, AI_CTX_SIZE)
        self.ctx_size_spin.setSingleStep(512)
        self.gpu_layers_spin = self._add_spin_row(layout, "GPU Слои (-1=все):", -1, 100, -1)
        self.gpu_device_spin = self._add_spin_row(layout, "GPU Device ID:", 0, 16, 0)
        
        self.backend_combo = QComboBox()
        self.backend_combo.addItems(["auto", "cuda", "cpu", "vulkan"])
        self.backend_combo.setStyleSheet(Components.text_input())
        layout.addWidget(QLabel("Backend:"))
        layout.addWidget(self.backend_combo)
        
        group.setLayout(layout)
        return group
    
    def _create_debug_settings(self) -> QGroupBox:
        group = self._create_group("Отладка")
        layout = QVBoxLayout()
        self.debug_mode_check = QCheckBox("Общая отладка")
        self.ai_debug_check = QCheckBox("Отладка AI")
        self.parser_debug_check = QCheckBox("Отладка парсера")
        for chk in [self.debug_mode_check, self.ai_debug_check, self.parser_debug_check]:
            chk.setStyleSheet(f"color: {Palette.TEXT};")
            layout.addWidget(chk)
        group.setLayout(layout)
        return group
    
    def _create_buttons(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.addStretch()
        btn_save = QPushButton("Сохранить")
        btn_save.setStyleSheet(Components.start_button())
        btn_save.clicked.connect(self._on_apply)
        layout.addWidget(btn_save)
        return layout
    
    def _populate_models(self):
        self.model_combo.clear()
        if os.path.exists(MODELS_DIR):
            for m in os.listdir(MODELS_DIR): 
                if m.endswith(".gguf"): self.model_combo.addItem(m)

    def _load_settings(self):
        # General
        self.request_delay_spin.setValue(self.current_settings.get("request_delay", 500))
        self.max_retries_spin.setValue(self.current_settings.get("max_retries", 3))
        self.page_timeout_spin.setValue(self.current_settings.get("page_timeout", 15))
        self.ctx_size_spin.setValue(self.current_settings.get("ai_ctx_size", AI_CTX_SIZE))
        self.gpu_layers_spin.setValue(self.current_settings.get("ai_gpu_layers", -1))
        self.gpu_device_spin.setValue(self.current_settings.get("ai_gpu_device", 0))
        
        # Telegram
        self.tg_token_input.setText(self.current_settings.get("telegram_token", ""))
        self.tg_chat_id_input.setText(self.current_settings.get("telegram_chat_id", ""))
        self.tg_interval_spin.setValue(self.current_settings.get("telegram_check_interval", 60))

        # Checkboxes
        self.debug_mode_check.setChecked(self.current_settings.get("debug_mode", False))
        self.ai_debug_check.setChecked(self.current_settings.get("ai_debug", False))
        self.parser_debug_check.setChecked(self.current_settings.get("parser_debug", False))
        
        model = self.current_settings.get("ai_model", "")
        if model:
            idx = self.model_combo.findText(model)
            if idx >= 0: self.model_combo.setCurrentIndex(idx)
            
        backend = self.current_settings.get("ai_backend", "auto")
        idx = self.backend_combo.findText(backend)
        if idx >= 0: self.backend_combo.setCurrentIndex(idx)
    
    def _on_apply(self):
        settings = {
            "request_delay": self.request_delay_spin.value(),
            "max_retries": self.max_retries_spin.value(),
            "page_timeout": self.page_timeout_spin.value(),
            "ai_ctx_size": self.ctx_size_spin.value(),
            "ai_gpu_layers": self.gpu_layers_spin.value(),
            "ai_gpu_device": self.gpu_device_spin.value(),
            "ai_backend": self.backend_combo.currentText(),
            "ai_model": self.model_combo.currentText(),
            "debug_mode": self.debug_mode_check.isChecked(),
            "ai_debug": self.ai_debug_check.isChecked(),
            "parser_debug": self.parser_debug_check.isChecked(),
            # New Telegram Settings
            "telegram_token": self.tg_token_input.text().strip(),
            "telegram_chat_id": self.tg_chat_id_input.text().strip(),
            "telegram_check_interval": self.tg_interval_spin.value()
        }
        self.current_settings = settings
        self.settings_changed.emit(settings)
        self.accept()
    
    def get_settings(self) -> dict: return self.current_settings