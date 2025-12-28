import os
import shutil
import requests
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QSpinBox, QCheckBox, QComboBox,
    QGroupBox, QLineEdit, QProgressBar, QMessageBox, 
    QWidget, QScrollArea, QFrame, QToolButton, QSizePolicy,
    QTextBrowser, QPlainTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QTimer
from app.ui.styles import Components, Palette, Typography, Spacing
from app.config import AI_CTX_SIZE, MODELS_DIR, DEFAULT_MODEL_NAME, BASE_APP_DIR

class CollapsibleBox(QWidget):
    """Виджет-аккордеон: Заголовок (кнопка) + Контент"""
    toggled = pyqtSignal(bool)  # Сигнал для внешнего управления (например, скроллом)

    def __init__(self, title="", parent=None, is_sub_level=False):
        super().__init__(parent)
        self.toggle_button = QToolButton(text=title, checkable=True, checked=False)
        self.toggle_button.setStyleSheet(f"""
            QToolButton {{
                border: none;
                background-color: transparent;
                color: {Palette.TEXT};
                font-weight: {'normal' if is_sub_level else 'bold'};
                font-size: {'13px' if is_sub_level else '14px'};
                text-align: left;
                padding: 5px;
            }}
            QToolButton:hover {{ color: {Palette.PRIMARY}; }}
            QToolButton:checked {{ color: {Palette.PRIMARY}; }}
        """)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle_button.clicked.connect(self.on_pressed)

        self.content_area = QWidget()
        self.content_area.setMaximumHeight(0)
        self.content_area.setMinimumHeight(0)
        self.content_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.animation = QPropertyAnimation(self.content_area, b"maximumHeight")
        self.animation.setDuration(300)
        # Важно: подключаем слот завершения анимации
        self.animation.finished.connect(self.on_animation_finished)

        lay = QVBoxLayout(self)
        lay.setSpacing(0)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.toggle_button)
        lay.addWidget(self.content_area)

    def on_pressed(self):
        checked = self.toggle_button.isChecked()
        self.toggle_button.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        
        if checked:
            # ПЕРЕД открытием пересчитываем геометрию, чтобы узнать требуемый размер
            self.content_area.updateGeometry()
            content_height = self.content_area.layout().sizeHint().height()
            
            self.animation.setStartValue(0)
            self.animation.setEndValue(content_height)
        else:
            # ПЕРЕД закрытием фиксируем текущую высоту (так как она может быть бесконечной)
            self.animation.setStartValue(self.content_area.height())
            self.animation.setEndValue(0)
            
        self.animation.start()
        self.toggled.emit(checked)

    def on_animation_finished(self):
        # Если коробка открыта, снимаем ограничение по высоте.
        # Это позволяет вложенным элементам растягивать родителя.
        if self.toggle_button.isChecked():
            self.content_area.setMaximumHeight(16777215) # MAX_INT (практически бесконечность)

    def set_content_layout(self, layout):
        self.content_area.setLayout(layout)

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

PATCH_HISTORY = {
    "1.1.5": """
    <h3>🕷 Парсер</h3>
    <ul>
        <li>Доработан механизм завершения всех процессов, которые могли оставаться не закрытыми после завершения работы парсера и вызывать дублирование в памяти.</li>
        <li>Улучшен способ обнаружения и остановки процессов парсера при выходе из приложения.</li>
    </ul>

    <h3>🧠 Нейросеть</h3>
    <ul>
        <li>Исправления, гарантирующие, что приложение не запустит второй процесс нейросети, пока текущий стартует или уже работает.</li>
        <li>В несколько раз уменьшен «спам» запросами к процессу нейросети при проверке статусов (старт/стоп, обновления чанков памяти), что улучшает отзывчивость при работе с большими объемами данных и снижает риск вылета приложения.</li>
        <li>Полностью переработан старт «культивации чанков» памяти:
            <ul>
                <li>Вместо одновременного запуска всей работы, каждый процесс формирования чанка добавляется в отдельную очередь, что немного медленнее, но гораздо стабильнее.</li>
                <li>Одновременно обрабатывается только один чанк памяти, что ускоряет общую работу, поскольку LLM больше не распыляет ресурсы на параллельный анализ всей памяти.</li>
                <li>Обновлена методика авто-старта нейросети, если она еще не поднята в момент, когда приложению нужно обновить память.</li>
            </ul>
        </li>
        <li>Механизм пользовательских инструкций обновлен и теперь учитывается в большинстве задач нейросети: при анализе объявлений, формировании памяти ИИ и в чате.</li>
        <li>Чат теперь учитывает "сырую" базу данных, добавленную через тумблер парсера «Поместить в память ИИ» (данные, не прошедшие культивацию), что дает ИИ больше точных данных для диалога.</li>
        <li>Чат теперь "знает" о текущей открытой таблице на странице «Парсера», что позволяет нейросети напрямую использовать контекст таблицы (в будущих версиях таблицы будут продублированы во вкладке «Аналитика»).</li>
        <li>Множественные улучшения очистки «сырых» результатов парсера, помещенных в память из таблицы результатов - снижает вероятность вылета из-за некорректной обработки таких данных нейросетью.</li>
        <li>При инициализации БД включается специальный режим, уменьшающий конфликты чтения/записи между потоками при параллельных операциях нейросети (например, анализ таблицы + актуализация памяти).</li>
        <li>Уменьшен след в оперативной памяти (RAM) в 2-3 раза без потери производительности или качества работы LLM.</li>
        <li>Уменьшено потребление памяти видеокарты (VRAM) в процедуре анализа объявлений.</li>
        <li>Изменен и ускорен метод определения "похожих" объявлений - анализ для столбца "Вердикт ИИ" теперь может происходить быстрее в 2-5 раз.</li>
        <li>Выполнен тюнинг внутренних параметров нейросети в разных контекстах (анализ, память, чат) для улучшения выводов LLM и качества общения.</li>
    </ul>

    <h3>🎨 Интерфейс</h3>
    <ul>
        <li>Вкладка «Аналитика» снова разблокирована. Сейчас в ней доступен чат, а виджет "Инструкции ИИ" перенесен на вкладку «Нейросеть».</li>
        <li>Панель "Инструкций ИИ" обновлена для лучшего опыта использования: улучшены карточки с текстом и кнопка удаления текущей инструкции.</li>
        <li>Журнал событий теперь логирует прогресс анализа нейросети (сколько элементов готово/осталось) и показывает общее время анализа от старта до завершения.</li>
        <li>Выбранные теги в выпадающем меню пресетов поиска теперь автоматически очищаются после применения к текущей или новой очереди, что предотвращает перенос "старых" отмеченных тегов в новую очередь.</li>
    </ul>

    <h3>⚙️ Общее</h3>
    <ul>
        <li>Удалено и очищено множество старой/нефункциональной логики: повышена производительность, снижены накладные расходы лишних запросов, уменьшен размер файлов приложения.</li>
    </ul>
""",
    "1.1.1": """
        <h3>🕷 Парсер</h3>
        <ul>
            <li>Теперь приложение сохраняет таблицы результатов поиска с таким же именем, как у очереди с которой был произведен поиск. Таким образом легко можно увидеть от какой очереди получилась таблица.</li>
            <li>Добавлена возможность выбрать существующую таблицу для "добавления результатов к ней" или "обновления результатов" даже при включенной опции "Разделять результаты очередей", что делает процесс обновления таблиц существенно быстрее и удобнее.</li>
            <li>Исправлен баг, когда приложение не сохраняло и сбрасывало все пользовательские имена очередй при перезапуске.</li>
            <li>Исправлена редкая проблема, которая создавала сценарий невозможности продолжения поиска по всем выбранным категориям очереди, если перед ней была очередь с "авто-категорией".</li>
        </ul>
    """,
    "1.1.0": """
        <h3>🕷 Парсер</h3>
        <ul>
            <li>Добавлено диалоговое окно, которое предлагает два сценария возможного поиска, если приложение обнаруживает, что в какой-либо включенной в поиск очереди, отсутствуют отсканированные категории. Пользователь может либо продолжить с "авто-категорией", которая обнаружит основную категорию для поискового запроса, либо выбрать вариант с предварительным сканированием и выбором категорий, а также их автоматическим применением к конкретной очереди, чтобы парсер работал именно по этим категориям, как при ручном сканировании. Это улучшает опыт использования парсера и избавляет от надобности дополнительных проверок для многочисленных очередей, в поисках отсканированных категорий.</li>
            <li>Возвращен столбец "Состояние" в таблицы, который указывает на состояние товара в объявлении, работает во всех режимах поиска (помещен между "Просмотрами" и "Датой").</li>
            <li>Исправлено несколько проблем связанных с очередями поиска, когда следующая очередь могла некорректно обновлять интерфейс и настроенную конфигурацию, а парсер мог игнорировать завершение предыдущей очереди и начало работы новой.</li>
            <li>Устранен баг, который не позволял перелистывать страницы сайта в режимах поиска "Полный" и "Нейро", что могло приводить к получению 50 объявлений в максимуме, даже когда пользователь запрашивал больше.</li>
            <li>Улучшен метод определения товара из поля "Подобрано для вас" для лучшего фильтра и отбраковки таких объявлений, поправлены найденные ошибки в рамках такой фильтрации. Теперь парсер будет оповещать пользователя (через Журнал событий), когда он пропускает объявление подобного характера.</li>
        </ul>

        <h3>🧠 Нейросеть</h3>
        <ul>
            <li>Нейросеть теперь всегда опирается на четыре основных принципа при анализе объявлений: наполнение таблицы (основные столбцы данных), системный промпт, инструкции пользователя (если доступны) и память.</li>
            <li>Анализ учитывает следующие столбцы таблицы по следующим критериям:
                <ul>
                    <li><strong>ЦЕНА:</strong> анализатор смотрит на среднюю цену и медиану в рамках такого же товара в конкретной таблице, после чего ищет совпадения в памяти нейросети и, если данных достаточно, то добавляет эти знания к текущему анализу; также учитывает инструкции пользователя, когда они доступны (в версии 1.1.5).</li>
                    <li><strong>ТОВАР:</strong> важный элемент для анализатора, который определяет его важность по системному промпту вдобавок к инструкциям пользователя, после чего сравнивает с памятью нейросети, чтобы навести LLM на лучший "чанк" памяти для использования в анализе.</li>
                    <li><strong>ПРОСМОТРЫ:</strong> если просмотров "0" (ноль), то анализатор не вкладывает этот столбец в общий процесс анализа, поскольку парсер мог не собрать данные для этого элемента (например, в режиме "Первичного" поиска); если это значение >0, то анализатор смотрит на соотношение цены и просмотров, чтобы лучше определять объявления "для привлечения внимания" или "бесконечно обновляемые объявления", тем самым занижая финальную оценку для этого товара в вердикте; косвенно подставляет дату публикации (обновления) объявления, чтобы получать еще более точные критерии.</li>
                    <li><strong>СОСТОЯНИЕ:</strong> довольно простой элемент для анализатора, который улучшает оценку для новых товаров или товаров в отличном состоянии, но постепенно уменьшает ее для Б/У, вплоть до самой худшей, если это "на запчасти".</li>
                    <li><strong>ДАТА:</strong> используется анализатором, помимо уже указанных случаев, как соотношение цены/предложения, что позволяет извлекать такое понятие как "дефицит", что делает товар привлекательнее в оценочной системе, если нет подозрений на соотношение цены/просмотра; также слишком старые объявления (более 30 дней от текущей даты) не имеют большой ценности.</li>
                    <li><strong>ОПИСАНИЕ:</strong> может быть очень важным элементом для анализатора, откуда нейросеть получит дополнительную информацию, которая может сильно поменять оценочный процесс, исходя из всех уже названных столбцов, системного промпта и инструкций пользователя (например, именно здесь LLM может наткнуться на факт "сломанного" товара или каких-то подозрительных условий выкупа, тогда как другие элементы могли не дать эту информацию).</li>
                </ul>
            </li>
            <li>Усовершенствован процесс сравнения объявлений друг с другом в рамках анализируемой таблицы и в памяти, что дает лучшие результаты в анализе, делая его более объективным. Улучшен процесс нахождения похожих товаров или категорий в памяти.</li>
            <li>Исправлен баг, когда в качестве опоры анализа использовалось поле "Доп. критерии ИИ", что являлось критической ошибкой дизайна. Это приводило к искажению анализа и ломало весь процесс.</li>
            <li>Улучшен смысловой вывод и форматирование вердикта нейросети, который записывается в столбец "Вердикт ИИ".</li>
            <li>Исправлена проблема нелогичной сортировки столбца "Вердикт ИИ", когда неизвестный статус вклинивался между хорошей и плохой сделкой.</li>
        </ul>

        <h3>🎨 Интерфейс</h3>
        <ul>
            <li>Пресеты тегов поиска и фильтров получили большое обновление. Основные новинки и изменения:
                <ul>
                    <li>Окно управления пресетами Поиска и Фильтрации теперь можно вызвать с обоих полей, чтобы обеспечивать более быструю навигацию.</li>
                    <li>Внутри этого окна изменился принцип добавления и редактирования тегов: теперь пользователь может создавать директории в основной папке выбранного набора, в том числе и вложенные, которые уже вмещают в себя теги. Это позволяет структурировать хранение тегов так, как того требует ваш рабочий процесс.</li>
                    <li>Директории и теги можно переименовывать и удалять.</li>
                    <li>По нажатию "звездочки" в полях Ищем и Исключаем, помимо управления пресетами, появляется выпадающее меню, которое содержит все созданные наборы и их директории с тегами, которые можно отметить и массово применить в нужно поле. Меню спроектировано так, чтобы можно было добавлять теги на оба поля сразу, избавляя пользователя от нужды переключаться между полями поиска и фильтрации.</li>
                    <li>Теперь можно добавить все выбранные теги как к текущей очереди, так и к новой очереди, которая будет создана автоматически с выбранными тегами.</li>
                </ul>
            </li>
            <li>"История изменений" по версиям приложения выведена в отдельную категорию в настройках и находится в самом низу этого окна. Это изменение убирает всплывающее окно с текстом обновления при старте приложение и создает единое место-хранилище, где пользователь может почитать историю изменений.</li>
        </ul>
    """,
    "1.0.7": """
        <h3>🕷 Парсер</h3>
        <ul>
            <li>Теперь поиск корректно учитывает все выбранные категории обхода вместе с регионами.</li>
            <li>Исправлена проблема загрузки устаревших категорий при запуске.</li>
        </ul>

        <h3>🎨 Интерфейс</h3>
        <ul>
            <li>Окно "Наборов черного списка" теперь не обрезается.</li>
            <li>Возвращена сортировка и подсказки столбца "Вердикт ИИ".</li>
        </ul>
    """,
    "1.0.6": """
            <h3>🕷 Парсер</h3>
        <ul>
            <li>Исправлен баг с невозможностью продолжить корректное логирование парсера/нейросети, что в том числе прерывало процесс поиска.</li>
        </ul>

        <h3>🎨 Интерфейс</h3>
        <ul>
            <li>Теперь главное окно приложения адаптируется под экраны любого размера, открываясь в центре и адаптируя свой размер автоматически.</li>
        </ul>
    """,
    "1.0.5": """
        <h3>🕷 Парсер</h3>
            <ul>
                <li><strong>Скорость:</strong> Оптимизирован сбор данных в режимах <span class="highlight">Полный</span> и <span class="highlight">Нейро</span>.</li>
                <li><strong>Анти-бан:</strong> Внедрены новые стратегии обхода мягких и полных блокировок.</li>
                <li><strong>Надежность:</strong> Добавлен альтернативный сценарий обработки "битых" страниц Авито.</li>
                <li><strong>Ресурсы:</strong> Исправлена очистка памяти при остановке. Запуск новой очереди после паузы теперь работает без сбоев.</li>
                <li>Множество исправлений стабильности ядра.</li>
            </ul>

            <h3>🧠 Нейросеть</h3>
            <ul>
                <li>Параметры "Нейро-анализ" и "Поместить в память ИИ" (как и их ручные версии) снова работают и выполняют свои функции.</li>
                <li>Вкладка "Аналитика" временно <span class="warning">заблокирована</span> для переработки.</li>
                <li>Управление ИИ перенесено в новую вкладку <strong>"Память"</strong>.</li>
                <li><strong>Долговременная память:</strong> ИИ теперь формирует базу знаний (чанки) по рынку, а не просто анализирует объявления в вакууме.</li>
                <li><strong>Smart Detection:</strong> Система сама находит популярные категории (например, >5 видеокарт) и предлагает их запомнить.</li>
                <li><strong>Динамический RAG:</strong> При анализе товара ИИ мгновенно ищет похожие знания в памяти и сравнивает цену с исторической медианой.</li>
                <li><strong>Live-режим:</strong> Если знаний еще нет, ИИ автоматически переключается на сухую математическую статистику.</li>
                <li><strong>Оптимизация:</strong> Устаревшие знания сжимаются на 75% без потери смысла.</li>
            </ul>

            <h3>🎨 Интерфейс</h3>
            <ul>
                <li><strong>Пресеты поиска:</strong> Исправлен критический баг с зацикливанием окна при добавлении нового тега.</li>
                <li>Обновлен дизайн и поведение кнопок в менеджере пресетов.</li>
            </ul>
    """,
    "1.0.0": "<ul><li>Релиз приложения.</li></ul>"
}

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
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(Components.scroll_area())
        self.scroll_area.verticalScrollBar().setStyleSheet(Components.global_scrollbar())
        
        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        self.content_layout.setSpacing(Spacing.LG) # Большой отступ между блоками

        # --- СЕКЦИИ НАСТРОЕК ---
        
        self.content_layout.addWidget(self._create_search_settings_section())
        self.content_layout.addWidget(self._create_divider())

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

        # Разделитель
        self.content_layout.addWidget(self._create_divider())

        # --- НОВАЯ СЕКЦИЯ: ИСТОРИЯ ОБНОВЛЕНИЙ ---
        self.content_layout.addWidget(self._create_patch_notes_section())

        self.content_layout.addStretch()
        
        self.scroll_area.setWidget(content_widget)
        root_layout.addWidget(self.scroll_area)

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

    def _create_search_settings_section(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        layout.addWidget(self._create_group_header("Фильтр Дефектов"))

        info = InfoBadge(
            "Словарь слов-паразитов.\n"
            "Если парсер найдет эти слова в описании или заголовке,\n"
            "товар будет пропущен (даже если цена подходит).\n"
            "Пишите слова через запятую.\n\n"
            "Базовые слова (сломан, разбит, труп, на запчасти) уже вшиты,\n"
            "их писать не нужно!"
        )
        
        lbl_row = QHBoxLayout()
        lbl = QLabel("Ваши стоп-слова (дополнительно к базовым):")
        lbl.setStyleSheet(f"color: {Palette.TEXT};")
        lbl_row.addWidget(lbl)
        lbl_row.addWidget(info)
        lbl_row.addStretch()
        layout.addLayout(lbl_row)

        self.defect_keywords_input = QPlainTextEdit()
        self.defect_keywords_input.setPlaceholderText("пример: рефаб, после ремонта, шумят дросселя, без коробки")
        self.defect_keywords_input.setMinimumHeight(80)
        self.defect_keywords_input.setStyleSheet(Components.text_input())
        
        layout.addWidget(self.defect_keywords_input)
        
        return container

    # --- PATCH NOTES SECTION ---
    def _create_patch_notes_section(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)

        # Главный "кат"
        main_box = CollapsibleBox("📜 ИСТОРИЯ ОБНОВЛЕНИЙ", is_sub_level=False)
        
        # Скролл к секции при открытии
        main_box.toggled.connect(lambda checked: 
            QTimer.singleShot(320, lambda: self.scroll_area.ensureWidgetVisible(main_box)) 
            if checked else None
        )

        versions_widget = QWidget()
        versions_layout = QVBoxLayout(versions_widget)
        versions_layout.setContentsMargins(Spacing.LG, 0, 0, 0)
        versions_layout.setSpacing(Spacing.XS)

        # --- ИЗМЕНЕНИЕ: Добавили enumerate для отслеживания индекса ---
        for i, (version, html_content) in enumerate(PATCH_HISTORY.items()):
            ver_box = CollapsibleBox(f"Версия {version}", is_sub_level=True)
            
            content_widget = QWidget()
            content_layout = QVBoxLayout(content_widget)
            content_layout.setContentsMargins(0, 5, 0, 15)
            
            browser = QTextBrowser()
            browser.setOpenExternalLinks(True)
            browser.setFrameShape(QFrame.Shape.NoFrame)
            browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            browser.setStyleSheet(f"""
                QTextBrowser {{
                    background-color: transparent;
                    color: {Palette.TEXT_SECONDARY};
                    font-size: 13px;
                    border: none;
                }}
            """)
            browser.setHtml(html_content)
            
            # Расчет высоты
            doc = browser.document()
            doc.setTextWidth(self.width() - 80)
            h = doc.documentLayout().documentSize().height() + 10 
            browser.setFixedHeight(int(h))
            
            content_layout.addWidget(browser)
            ver_box.set_content_layout(content_layout)
            
            # --- НОВАЯ ЛОГИКА: Если это первый элемент (i==0), открываем его ---
            if i == 0:
                ver_box.toggle_button.setChecked(True)
                ver_box.on_pressed() # Программно вызываем открытие

            versions_layout.addWidget(ver_box)

        main_box.set_content_layout(versions_layout)
        layout.addWidget(main_box)

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
        keywords = self.current_settings.get("user_defect_keywords", "")
        if isinstance(keywords, list):
            keywords = ", ".join(keywords)
        self.defect_keywords_input.setPlainText(keywords)

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
            "user_defect_keywords": self.defect_keywords_input.toPlainText().replace("\n", ","),
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