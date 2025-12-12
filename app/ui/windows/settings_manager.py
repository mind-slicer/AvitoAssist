import os
import shutil
import requests
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QSpinBox, QCheckBox, QComboBox,
    QGroupBox, QLineEdit, QProgressBar, QMessageBox, 
    QWidget, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from app.ui.styles import Components, Palette, Typography, Spacing
from app.config import AI_CTX_SIZE, MODELS_DIR, DEFAULT_MODEL_NAME, BASE_APP_DIR

class InfoBadge(QLabel):
    """Маленький значок (i) с подсказкой"""
    def __init__(self, tooltip_text, parent=None):
        super().__init__("i", parent)
        self.setToolTip(tooltip_text)
        self.setFixedSize(20, 20)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {Palette.BG_DARK_3};
                color: {Palette.TEXT_SECONDARY};
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: 10px;
                font-weight: bold;
                font-family: {Typography.MONO};
                font-size: 12px;
            }}
            QLabel:hover {{
                background-color: {Palette.PRIMARY};
                color: {Palette.TEXT_ON_PRIMARY};
                border-color: {Palette.PRIMARY};
            }}
        """)

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
        self.resize(650, 750) # Чуть выше, так как теперь скролл
        self.setStyleSheet(Components.dialog())
        self._init_ui()
        self._load_settings()
    
    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Заголовок окна (внутри контента)
        header = QWidget()
        header.setStyleSheet(f"background-color: {Palette.BG_DARK_2}; border-bottom: 1px solid {Palette.BORDER_SOFT};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        title = QLabel("НАСТРОЙКИ ПРИЛОЖЕНИЯ")
        title.setStyleSheet(Components.section_title())
        header_layout.addWidget(title)
        root_layout.addWidget(header)

        # 2. Область прокрутки
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(Components.scroll_area())
        scroll.verticalScrollBar().setStyleSheet(Components.global_scrollbar())
        
        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        self.content_layout.setSpacing(Spacing.LG) # Большой отступ между блоками

        # --- СЕКЦИИ НАСТРОЕК ---
        
        # Блок ИИ
        self.content_layout.addWidget(self._create_ai_settings())
        
        # Блок Скачивания (встроен в поток)
        self.content_layout.addWidget(self._create_model_download_section())
        
        # Разделитель
        self.content_layout.addWidget(self._create_divider())
        
        # Блок Telegram
        self.content_layout.addWidget(self._create_telegram_settings())
        
        # Разделитель
        self.content_layout.addWidget(self._create_divider())
        
        # Блок Система
        self.content_layout.addWidget(self._create_system_settings())

        self.content_layout.addStretch()
        
        scroll.setWidget(content_widget)
        root_layout.addWidget(scroll)

        # 3. Нижняя панель с кнопками
        footer = QWidget()
        footer.setStyleSheet(f"background-color: {Palette.BG_DARK_2}; border-top: 1px solid {Palette.BORDER_SOFT};")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        
        btn_cancel = QPushButton("Отмена")
        btn_cancel.setStyleSheet(f"""
            QPushButton {{ 
                background: transparent; border: 1px solid {Palette.BORDER_SOFT}; 
                color: {Palette.TEXT_MUTED}; border-radius: {Spacing.RADIUS_NORMAL}px; padding: 8px 16px;
            }}
            QPushButton:hover {{ background: {Palette.BG_DARK_3}; color: {Palette.TEXT}; }}
        """)
        btn_cancel.clicked.connect(self.reject)
        
        btn_save = QPushButton("Сохранить и закрыть")
        btn_save.setStyleSheet(Components.start_button())
        btn_save.clicked.connect(self._on_apply)
        
        footer_layout.addStretch()
        footer_layout.addWidget(btn_cancel)
        footer_layout.addWidget(btn_save)
        
        root_layout.addWidget(footer)

    def _create_divider(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet(f"background-color: {Palette.DIVIDER}; border: none; min-height: 1px; max-height: 1px;")
        return line

    def _create_group_header(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {Palette.PRIMARY}; font-size: 14px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px;")
        return lbl

    # --- AI SETTINGS ---
    def _create_ai_settings(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)
        
        layout.addWidget(self._create_group_header("Нейросеть"))

        # Модель
        self.model_combo = QComboBox()
        self.model_combo.setStyleSheet(Components.styled_combobox())
        self._populate_models()
        layout.addLayout(self._create_labeled_row("Активная модель:", self.model_combo, 
            "Файл 'мозгов' нейросети. Если список пуст, скачайте модель ниже."))
        
        # Контекст
        self.ctx_size_spin = self._create_spin(512, 32768, AI_CTX_SIZE, step=512)
        layout.addLayout(self._create_labeled_row("Размер контекста:", self.ctx_size_spin,
            "Сколько текста ИИ может 'держать в голове' одновременно.\n"
            "Чем больше число, тем больше объявлений он запомнит для анализа,\n"
            "но тем больше оперативной памяти (RAM) потребуется.\n"
            "Рекомендуется: 4096 или 8192."))

        # GPU Layers
        self.gpu_layers_spin = self._create_spin(-1, 200, -1)
        layout.addLayout(self._create_labeled_row("Слои на видеокарте (GPU):", self.gpu_layers_spin,
            "Сколько частей нейросети перенести на видеокарту для ускорения.\n"
            "-1 = перенести ВСЁ (самый быстрый вариант).\n"
            "0 = работать только на процессоре (медленно).\n"
            "Ставьте -1, если у вас хорошая видеокарта."))

        # GPU Device
        self.gpu_device_spin = self._create_spin(0, 16, 0)
        layout.addLayout(self._create_labeled_row("ID видеокарты:", self.gpu_device_spin,
            "Номер видеокарты в системе, если их несколько.\n"
            "Для большинства компьютеров с одной картой — это 0."))

        # Backend
        self.backend_combo = QComboBox()
        self.backend_combo.addItems(["auto", "cuda", "cpu", "vulkan"])
        self.backend_combo.setStyleSheet(Components.styled_combobox())
        layout.addLayout(self._create_labeled_row("Движок запуска (Backend):", self.backend_combo,
            "Технология запуска нейросети.\n"
            "• Auto: программа сама выберет лучшее.\n"
            "• CUDA: для карт NVIDIA (быстро).\n"
            "• Vulkan: для карт AMD/Intel.\n"
            "• CPU: работа только на процессоре (если нет видеокарты)."))

        return container

    def _create_spin(self, min_v, max_v, default, step=1):
        spin = QSpinBox()
        spin.setRange(min_v, max_v)
        spin.setValue(default)
        spin.setSingleStep(step)
        spin.setStyleSheet(Components.text_input())
        return spin

    def _create_labeled_row(self, label_text, widget, tooltip_text=None):
        row = QHBoxLayout()
        row.setSpacing(Spacing.SM)
        
        lbl = QLabel(label_text)
        lbl.setMinimumWidth(180)
        lbl.setStyleSheet(f"color: {Palette.TEXT}; font-size: 14px;")
        row.addWidget(lbl)
        
        if tooltip_text:
            badge = InfoBadge(tooltip_text)
            row.addWidget(badge)
        
        row.addWidget(widget, 1) # Widget stretches
        return row

    # --- MODEL DOWNLOAD ---
    def _create_model_download_section(self) -> QGroupBox:
        group = QGroupBox()
        group.setStyleSheet(f"""
            QGroupBox {{ 
                background-color: {Palette.with_alpha(Palette.BG_DARK_3, 0.5)}; 
                border: 1px dashed {Palette.BORDER_SOFT}; 
                border-radius: {Spacing.RADIUS_NORMAL}px;
            }}
        """)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.SM)
        
        top_row = QHBoxLayout()
        title = QLabel("Скачивание базовой модели")
        title.setStyleSheet(f"color: {Palette.TEXT_SECONDARY}; font-weight: bold;")
        
        info_label = QLabel(f"({DEFAULT_MODEL_NAME} ~4.1 ГБ)")
        info_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 12px;")
        
        top_row.addWidget(title)
        top_row.addWidget(info_label)
        top_row.addStretch()
        layout.addLayout(top_row)
        
        action_row = QHBoxLayout()
        self.btn_download_model = QPushButton("📥 Загрузить модель")
        self.btn_download_model.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_download_model.setStyleSheet(Components.start_button()) # Используем оранжевую кнопку
        self.btn_download_model.clicked.connect(self._on_download_model)
        
        self.btn_cancel_download = QPushButton("Отмена")
        self.btn_cancel_download.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel_download.setStyleSheet(Components.stop_button())
        self.btn_cancel_download.clicked.connect(self._on_cancel_download)
        self.btn_cancel_download.setVisible(False)
        
        action_row.addWidget(self.btn_download_model)
        action_row.addWidget(self.btn_cancel_download)
        layout.addLayout(action_row)
        
        self.download_progress = QProgressBar()
        self.download_progress.setVisible(False)
        self.download_progress.setStyleSheet(Components.progress_bar(Palette.SUCCESS))
        layout.addWidget(self.download_progress)
        
        self.download_status = QLabel("")
        self.download_status.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 12px;")
        self.download_status.setVisible(False)
        layout.addWidget(self.download_status)
        
        return group

    # --- TELEGRAM ---
    def _create_telegram_settings(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        header_row = QHBoxLayout()
        header_row.addWidget(self._create_group_header("Уведомления Telegram"))
        
        # Инструкция в виде значка (i)
        help_tg = InfoBadge(
            "Как настроить:\n"
            "1. Найдите бота @BotFather в Telegram, создайте нового бота и скопируйте Token.\n"
            "2. Найдите бота @userinfobot, чтобы узнать свой Chat ID (число).\n"
            "3. Введите данные ниже и нажмите 'Проверить'."
        )
        header_row.addWidget(help_tg)
        header_row.addStretch()
        layout.addLayout(header_row)

        self.tg_token_input = QLineEdit()
        self.tg_token_input.setPlaceholderText("Токен бота (например: 123456:ABC-DEF...)")
        self.tg_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.tg_token_input.setStyleSheet(Components.text_input())
        
        self.tg_chat_id_input = QLineEdit()
        self.tg_chat_id_input.setPlaceholderText("Ваш Chat ID (например: 123456789)")
        self.tg_chat_id_input.setStyleSheet(Components.text_input())

        layout.addLayout(self._create_labeled_row("Bot Token:", self.tg_token_input))
        layout.addLayout(self._create_labeled_row("Chat ID:", self.tg_chat_id_input))

        self.tg_interval_spin = self._create_spin(5, 1440, 60)
        self.tg_interval_spin.setSuffix(" мин")
        layout.addLayout(self._create_labeled_row("Проверка избранного:", self.tg_interval_spin, 
            "Как часто бот будет проверять изменение цены у товаров,\nкоторые вы добавили в 'Избранное' (звездочкой)."))

        self.btn_test_tg = QPushButton("📨 Отправить тестовое сообщение")
        self.btn_test_tg.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_test_tg.setStyleSheet(Components.small_button())
        self.btn_test_tg.clicked.connect(self._test_telegram)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_test_tg)
        layout.addLayout(btn_layout)
        
        return container

    # --- SYSTEM ---
    def _create_system_settings(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        layout.addWidget(self._create_group_header("Система и Отладка"))
        
        # Чекбоксы отладки
        debug_group = QVBoxLayout()
        debug_group.setSpacing(Spacing.SM)
        
        self.debug_mode_check = QCheckBox("Включить общие логи отладки (debug.log)")
        self.debug_mode_check.setStyleSheet(Components.styled_checkbox())
        
        self.ai_debug_check = QCheckBox("Подробные логи ИИ (показывает, о чем думает нейросеть)")
        self.ai_debug_check.setStyleSheet(Components.styled_checkbox())
        
        self.parser_debug_check = QCheckBox("Логи парсера (техническая информация)")
        self.parser_debug_check.setStyleSheet(Components.styled_checkbox())
        
        debug_group.addWidget(self.debug_mode_check)
        debug_group.addWidget(self.ai_debug_check)
        debug_group.addWidget(self.parser_debug_check)
        layout.addLayout(debug_group)
        
        # Зона опасности
        danger_frame = QFrame()
        danger_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Palette.with_alpha(Palette.ERROR, 0.1)};
                border: 1px solid {Palette.with_alpha(Palette.ERROR, 0.3)};
                border-radius: {Spacing.RADIUS_NORMAL}px;
            }}
        """)
        danger_layout = QHBoxLayout(danger_frame)
        danger_layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        
        warn_lbl = QLabel("Полный сброс настроек:")
        warn_lbl.setStyleSheet(f"color: {Palette.ERROR}; font-weight: bold;")
        
        btn_reset = QPushButton("Сбросить всё")
        btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reset.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_DARK};
                border: 1px solid {Palette.ERROR};
                color: {Palette.ERROR};
                border-radius: {Spacing.RADIUS_NORMAL}px;
                padding: 6px 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {Palette.ERROR}; color: {Palette.TEXT_ON_PRIMARY}; }}
        """)
        btn_reset.clicked.connect(self._on_factory_reset)
        
        danger_layout.addWidget(warn_lbl)
        danger_layout.addStretch()
        danger_layout.addWidget(btn_reset)
        
        layout.addWidget(danger_frame)
        
        return container

    # --- LOGIC ---

    def _test_telegram(self):
        token = self.tg_token_input.text().strip()
        chat_id = self.tg_chat_id_input.text().strip()
        
        if not token or not chat_id:
            QMessageBox.warning(self, "Ошибка", "Заполните Token и Chat ID перед проверкой.")
            return
            
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            resp = requests.post(url, json={"chat_id": chat_id, "text": "🤖 Avito Assist: Связь установлена успешно!"}, timeout=5)
            if resp.status_code == 200:
                QMessageBox.information(self, "Успех", "Сообщение отправлено! Проверьте свой Telegram.")
            else:
                QMessageBox.warning(self, "Ошибка Telegram API", f"Сервер ответил ошибкой:\nКод: {resp.status_code}\n{resp.text}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сети", f"Не удалось подключиться к Telegram:\n{e}")

    def _on_factory_reset(self):
        import sys
        import subprocess
        from PyQt6.QtWidgets import QApplication

        confirm = QMessageBox.warning(
            self, "Опасное действие", 
            "Вы действительно хотите сбросить настройки?\n\n"
            "• Все настройки будут удалены\n"
            "• База знаний ИИ (RAG) будет очищена\n"
            "• Приложение перезапустится\n\n"
            "Ваши сохраненные Excel/JSON файлы останутся.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if confirm == QMessageBox.StandardButton.Yes:
            files_to_remove = [
                "app_settings.json", 
                "queues_state.json", 
                "tag_presets.json",
                "tag_presets_ignore.json",
                "categories_cache.json",
                "avito_cookies.pkl",
                "debug.log"
            ]
            data_dir = os.path.join(BASE_APP_DIR, "data")
            
            try:
                for f in files_to_remove:
                    path = os.path.join(BASE_APP_DIR, f)
                    if os.path.exists(path):
                        try: os.remove(path)
                        except: pass
                
                if os.path.exists(data_dir):
                    shutil.rmtree(data_dir, ignore_errors=True)
                    
                executable = sys.executable
                args = sys.argv if not getattr(sys, 'frozen', False) else []
                subprocess.Popen([executable] + args)
                QApplication.quit()
                
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось выполнить сброс: {e}")

    def _on_download_model(self):
        from app.core.model_downloader import ModelDownloader
        if not self.model_downloader:
            self.model_downloader = ModelDownloader()
            self.model_downloader.progress_updated.connect(self._on_download_progress)
            self.model_downloader.download_finished.connect(self._on_download_finished)
            self.model_downloader.download_failed.connect(self._on_download_failed)
        
        self.btn_download_model.setEnabled(False)
        self.btn_download_model.setText("Загрузка...")
        self.btn_cancel_download.setVisible(True)
        self.download_progress.setVisible(True)
        self.download_status.setVisible(True)
        self.model_downloader.start_download()

    def _on_cancel_download(self):
        if self.model_downloader: self.model_downloader.cancel_download()
    
    def _on_download_progress(self, pct, d_mb, t_mb, speed):
        self.download_progress.setValue(pct)
        self.download_status.setText(f"Скорость: {speed} | Скачано: {d_mb:.1f} из {t_mb:.1f} MB")
    
    def _on_download_finished(self, path):
        self.download_progress.setValue(100)
        self.download_status.setText("Загрузка завершена успешно!")
        self.btn_cancel_download.setVisible(False)
        self.btn_download_model.setEnabled(True)
        self.btn_download_model.setText("✅ Скачано")
        self._populate_models()
        self.model_downloaded.emit(path)

    def _on_download_failed(self, msg):
        self.download_status.setText(f"Ошибка: {msg}")
        self.btn_cancel_download.setVisible(False)
        self.btn_download_model.setEnabled(True)
        self.btn_download_model.setText("Повторить")

    def _populate_models(self):
        self.model_combo.clear()
        if os.path.exists(MODELS_DIR):
            for m in os.listdir(MODELS_DIR): 
                if m.endswith(".gguf"): self.model_combo.addItem(m)

    def _load_settings(self):
        # AI
        self.ctx_size_spin.setValue(self.current_settings.get("ai_ctx_size", AI_CTX_SIZE))
        self.gpu_layers_spin.setValue(self.current_settings.get("ai_gpu_layers", -1))
        self.gpu_device_spin.setValue(self.current_settings.get("ai_gpu_device", 0))
        
        model = self.current_settings.get("ai_model", "")
        if model:
            idx = self.model_combo.findText(model)
            if idx >= 0: self.model_combo.setCurrentIndex(idx)
            
        backend = self.current_settings.get("ai_backend", "auto")
        idx = self.backend_combo.findText(backend)
        if idx >= 0: self.backend_combo.setCurrentIndex(idx)

        # Telegram
        self.tg_token_input.setText(self.current_settings.get("telegram_token", ""))
        self.tg_chat_id_input.setText(self.current_settings.get("telegram_chat_id", ""))
        self.tg_interval_spin.setValue(self.current_settings.get("telegram_check_interval", 60))

        # Checkboxes
        self.debug_mode_check.setChecked(self.current_settings.get("debug_mode", False))
        self.ai_debug_check.setChecked(self.current_settings.get("ai_debug", False))
        self.parser_debug_check.setChecked(self.current_settings.get("parser_debug", False))
    
    def _on_apply(self):
        # Собираем новые настройки
        new_settings = {
            "ai_ctx_size": self.ctx_size_spin.value(),
            "ai_gpu_layers": self.gpu_layers_spin.value(),
            "ai_gpu_device": self.gpu_device_spin.value(),
            "ai_backend": self.backend_combo.currentText(),
            "ai_model": self.model_combo.currentText(),
            "debug_mode": self.debug_mode_check.isChecked(),
            "ai_debug": self.ai_debug_check.isChecked(),
            "parser_debug": self.parser_debug_check.isChecked(),
            "telegram_token": self.tg_token_input.text().strip(),
            "telegram_chat_id": self.tg_chat_id_input.text().strip(),
            "telegram_check_interval": self.tg_interval_spin.value()
        }

        # ВАЖНО: Мы сохраняем старые настройки парсера (которые удалили из UI),
        # чтобы они не исчезли из конфига, если они там были.
        # Просто копируем их из self.current_settings в new_settings
        preserved_keys = ["request_delay", "max_retries", "page_timeout"]
        for key in preserved_keys:
            if key in self.current_settings:
                new_settings[key] = self.current_settings[key]

        self.current_settings = new_settings
        self.settings_changed.emit(new_settings)
        self.accept()
    
    def get_settings(self) -> dict: return self.current_settings