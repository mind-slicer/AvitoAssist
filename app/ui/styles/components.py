from app.ui.styles import Palette, Spacing, Typography

class Components:
    """
    Система компонентов для единообразного стиля UI.
    """
    
    # White Checkmark (16x16)
    ICON_CHECK_PNG = "url(C:/Users/MindSlicer/Desktop/3388530.png)"
    
    # White Down Arrow (12x12)
    ICON_ARROW_DOWN_PNG = "url(data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAwAAAAMCAYAAABWdVznAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAB3RJTUUH5QwWBBs0k/R8gQAAAB1pVFh0Q29tbWVudAAAAAAAQ3JlYXRlZCB3aXRoIEdJTVBkLmUHAAAAXUlEQVQoz2NgoDH4z8DAwMTAwCDDAA0G+P///4+B8T8D438Gxv8MjP8ZGP8zMP5nYPzPwPifgfE/A+N/Bsb/DIz/GRj/MzD+Z2D8z8D4n4HxPwPjf4Q0/v///z8DAPQDE4U0727kAAAAAElFTkSuQmCC)"

    @staticmethod
    def start_button() -> str:
        """Основная кнопка (оранжевая)"""
        return (
            f"QPushButton {{\n"
            f"    background-color: {Palette.PRIMARY};\n"
            f"    color: {Palette.TEXT_ON_PRIMARY};\n"
            f"    border: 1px solid {Palette.PRIMARY};\n"
            f"    border-radius: {Spacing.RADIUS_NORMAL}px;\n"
            f"    padding: {Spacing.PADDING_BUTTON[0]}px {Spacing.PADDING_BUTTON[1]}px;\n"  # ЭТАП 2: увеличено
            f"    font-family: {Typography.UI};\n"
            f"    font-size: {Typography.SIZE_MD}px;\n"
            f"    font-weight: {Typography.WEIGHT_BOLD};\n"
            f"}}\n"
            f"QPushButton:hover {{\n"
            f"    background-color: {Palette.PRIMARY_DARK};\n"
            f"    border-color: {Palette.PRIMARY_DARK};\n"
            f"}}\n"
            f"QPushButton:pressed {{\n"
            f"    background-color: {Palette.PRIMARY_DARK};\n"
            f"    padding-top: {Spacing.PADDING_BUTTON[0] + 1}px;\n"
            f"}}\n"
            f"QPushButton:disabled {{\n"
            f"    background-color: {Palette.with_alpha(Palette.PRIMARY, 0.4)};\n"
            f"    border-color: {Palette.with_alpha(Palette.PRIMARY, 0.4)};\n"
            f"    color: {Palette.TEXT_MUTED};\n"
            f"}}\n"
            f""
        )
    
    @staticmethod
    def stop_button() -> str:
        """Вторичная кнопка (серая)"""
        return (
            f"QPushButton {{\n"
            f"    background-color: {Palette.ERROR};\n"
            f"    color: {Palette.TEXT_ON_PRIMARY};\n"
            f"    border: 1px solid {Palette.ERROR};\n"
            f"    border-radius: {Spacing.RADIUS_NORMAL}px;\n"
            f"    padding: {Spacing.PADDING_BUTTON[0]}px {Spacing.PADDING_BUTTON[1]}px;\n"
            f"    font-family: {Typography.UI};\n"
            f"    font-size: {Typography.SIZE_MD}px;\n"
            f"    font-weight: {Typography.WEIGHT_BOLD};\n"
            f"}}\n"
            f"QPushButton:hover {{\n"
            f"    background-color: #ff6b6b;\n"
            f"    border-color: #ff6b6b;\n"
            f"}}\n"
            f"QPushButton:pressed {{\n"
            f"    background-color: #ff6b6b;\n"
            f"    border-color: {Palette.SECONDARY_DARK};\n"
            f"}}\n"
            f"QPushButton:disabled {{\n"
            f"    background-color: {Palette.with_alpha(Palette.ERROR, 0.4)};\n"
            f"    border-color: {Palette.with_alpha(Palette.ERROR, 0.4)};\n"
            f"    color: {Palette.TEXT_MUTED};\n"
            f"}}\n"
            f""
        )

    @staticmethod
    def small_button() -> str:
        """Маленькая кнопка"""
        return (
            f"QPushButton {{\n"
            f"    background-color: {Palette.BG_DARK_3};\n"
            f"    border: 1px solid {Palette.BORDER_PRIMARY};\n"
            f"    border-radius: {Spacing.RADIUS_NORMAL}px;\n"
            f"    color: {Palette.TEXT_SECONDARY};\n"
            f"    font-weight: {Typography.WEIGHT_BOLD};\n"
            f"    padding: XS MD;\n"
            f"}}\n"
            f"QPushButton:hover {{\n"
            f"    background-color: {Palette.BG_LIGHT};\n"
            f"    border-color: {Palette.TEXT_SECONDARY};\n"
            f"    color: {Palette.TEXT};\n"
            f"}}\n"
            f"QPushButton:pressed {{\n"
            f"    background-color: {Palette.BG_DARK_3};\n"
            f"}}\n"
            f""
        )
    
    @staticmethod
    def text_input() -> str:
        """Поля ввода с подработкой - ЭТАП 3 версия"""
        return (
            f"QSpinBox, QLineEdit, QComboBox, QPlainTextEdit {{\n"
            f"    background-color: {Palette.BG_LIGHT};\n"
            f"    border: 1px solid {Palette.BORDER_PRIMARY};\n"
            f"    border-radius: {Spacing.RADIUS_NORMAL}px;\n"
            f"    padding: {Spacing.PADDING_INPUT[0]}px {Spacing.PADDING_INPUT[1]}px;\n"  # Увеличено в ЭТАП 2
            f"    color: {Palette.TEXT};\n"
            f"    font-family: {Typography.UI};\n"
            f"    font-size: {Typography.SIZE_MD}px;\n"
            f"    line-height: {Typography.LINE_NORMAL};\n"  # ДОБАВЛЕНО: явная высота строки
            f"    selection-background-color: {Palette.PRIMARY};\n"
            f"    selection-color: {Palette.TEXT_ON_PRIMARY};\n"
            f"}}\n"
            f"QSpinBox:hover, QLineEdit:hover, QComboBox:hover, QPlainTextEdit:hover {{\n"
            f"    border-color: {Palette.TEXT_SECONDARY};\n"
            f"    background-color: {Palette.BG_LIGHT};\n"
            f"}}\n"
            f"QSpinBox:focus, QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{\n"
            f"    border-color: {Palette.PRIMARY};\n"
            f"    background-color: {Palette.BG_DARK_2};\n"
            f"    border: 2px solid {Palette.PRIMARY};\n"
            f"}}\n"
            f"QSpinBox:disabled, QLineEdit:disabled, QComboBox:disabled, QPlainTextEdit:disabled {{\n"
            f"    background-color: {Palette.BG_DARK_3};\n"
            f"    color: {Palette.TEXT_MUTED};\n"
            f"    border-color: {Palette.DIVIDER};\n"
            f"}}\n"
            f"QSpinBox::up-button, QSpinBox::down-button {{\n"
            f"    subcontrol-origin: border;\n"
            f"    width: 20px;\n"  # БЫЛО: 18 → 20px (больше)
            f"    background-color: {Palette.BG_DARK_3};\n"
            f"    border-left: 1px solid {Palette.BORDER_PRIMARY};\n"  # БЫЛО: BORDER_SOFT
            f"}}\n"
            f"QSpinBox::up-button:hover, QSpinBox::down-button:hover {{\n"
            f"    background-color: {Palette.SECONDARY};\n"
            f"}}\n"
            f"QSpinBox::up-arrow, QSpinBox::down-arrow {{\n"
            f"    width: 10px;\n"
            f"    height: 4px;\n"
            f"    color: {Palette.TEXT_SECONDARY};\n"  # БЫЛО: TEXT_SECONDARY → более контрастно
            f"}}\n"
            f""
        )

    @staticmethod
    def styled_combobox() -> str:
        """Комбо-бокс с видимой стрелкой и фиксированным направлением"""
        return (
            f"QComboBox {{\n"
            f"  background-color: {Palette.BG_LIGHT};\n"
            f"  border: 1px solid {Palette.BORDER_PRIMARY};\n"
            f"  border-radius: {Spacing.RADIUS_NORMAL}px;\n"
            f"  padding: {Spacing.PADDING_INPUT[0]}px {Spacing.PADDING_INPUT[1]}px;\n"
            f"  padding-right: 30px;\n"  # ДОБАВЛЕНО: место для стрелки
            f"  color: {Palette.TEXT};\n"
            f"  font-family: {Typography.UI};\n"
            f"  font-size: {Typography.SIZE_MD}px;\n"
            f"  selection-background-color: {Palette.PRIMARY};\n"
            f"  selection-color: {Palette.TEXT_ON_PRIMARY};\n"
            f"}}\n"
            f"QComboBox:hover {{\n"
            f"  border-color: {Palette.TEXT_SECONDARY};\n"
            f"  background-color: {Palette.BG_LIGHT};\n"
            f"}}\n"
            f"QComboBox:focus {{\n"
            f"  border: 2px solid {Palette.PRIMARY};\n"
            f"  background-color: {Palette.BG_DARK_2};\n"
            f"  outline: none;\n"
            f"}}\n"
            f"QComboBox::drop-down {{\n"
            f"  subcontrol-origin: padding;\n"
            f"  subcontrol-position: center right;\n"
            f"  width: 24px;\n"
            f"  border: none;\n"
            f"  background-color: transparent;\n"
            f"}}\n"
            f"QComboBox::drop-down:hover {{\n"
            f"  background-color: {Palette.with_alpha(Palette.PRIMARY, 0.15)};\n"
            f"  border-radius: {Spacing.RADIUS_NORMAL}px;\n"
            f"}}\n"
            f"QComboBox::down-arrow {{\n"
            f"  image: none;\n"  # Убираем PNG
            f"  width: 0;\n"
            f"  height: 0;\n"
            f"  border-left: 5px solid transparent;\n"  # CSS треугольник
            f"  border-right: 5px solid transparent;\n"
            f"  border-top: 6px solid {Palette.PRIMARY};\n"  # Оранжевая стрелка!
            f"  margin-right: 8px;\n"
            f"}}\n"
            f"QComboBox::down-arrow:hover {{\n"
            f"  border-top-color: {Palette.PRIMARY_DARK};\n"
            f"}}\n"
            f"QComboBox QAbstractItemView {{\n"
            f"  background-color: {Palette.BG_DARK_2};\n"
            f"  border: 1px solid {Palette.BORDER_PRIMARY};\n"
            f"  border-top: 2px solid {Palette.PRIMARY};\n"
            f"  selection-background-color: {Palette.with_alpha(Palette.PRIMARY, 0.25)};\n"
            f"  selection-color: {Palette.TEXT};\n"
            f"  outline: none;\n"
            f"  border-radius: {Spacing.RADIUS_NORMAL}px;\n"
            f"}}\n"
            f"QComboBox QAbstractItemView::item:hover {{\n"
            f"  background-color: {Palette.with_alpha(Palette.PRIMARY, 0.15)};\n"
            f"}}\n"
            f""
        )

    @staticmethod
    def styled_checkbox() -> str:
        """Checkbox с улучшенной видимостью - ЭТАП 3D"""
        return (
            f"QCheckBox {{\n"
            f"    color: {Palette.TEXT_SECONDARY};\n"  # БЫЛО: TEXT_SECONDARY → теперь белый
            f"    font-family: {Typography.UI};\n"
            f"    font-size: {Typography.SIZE_MD}px;\n"  # ДОБАВЛЕНО: явный размер
            f"    spacing: {Spacing.MD}px;\n"  # БЫЛО: SM → больше места между checkbox и текстом
            f"}}\n"
            f"QCheckBox::indicator {{\n"
            f"    width: 20px; height: 20px;\n"  # БЫЛО: 18 → 20px (больше)
            f"    border: 2px solid {Palette.BORDER_PRIMARY};\n"  # БЫЛО: 1px BORDER_SOFT → 2px PRIMARY
            f"    border-radius: 4px;\n"
            f"    background-color: {Palette.BG_DARK_3};\n"
            f"}}\n"
            f"QCheckBox::indicator:hover {{\n"
            f"    border-color: {Palette.PRIMARY};\n"
            f"    background-color: {Palette.with_alpha(Palette.PRIMARY, 0.1)};\n"  # ДОБАВЛЕНО: hover фон
            f"}}\n"
            f"QCheckBox::indicator:checked {{\n"
            f"    background-color: {Palette.PRIMARY};\n"
            f"    border-color: {Palette.PRIMARY};\n"
            f"    image: {Components.ICON_CHECK_PNG};\n"
            f"}}\n"
            "QCheckBox::indicator:checked:disabled {\n"
            f"    background-color: {Palette.PRIMARY};\n"
            f"    border-color: {Palette.PRIMARY};\n"
            f"    image: {Components.ICON_CHECK_PNG};\n"
            "}\n"
            f"QCheckBox::indicator:checked:hover {{\n"
            f"    background-color: {Palette.PRIMARY_DARK};\n"  # ДОБАВЛЕНО: hover для checked
            f"}}\n"
            f"QCheckBox:disabled {{\n"
            f"    color: {Palette.TEXT_MUTED};\n"
            f"}}\n"
            f"QCheckBox::indicator:disabled {{\n"
            f"    background-color: {Palette.BG_DARK};\n"
            f"    border-color: {Palette.DIVIDER};\n"
            f"}}\n"
            f""
        )

    @staticmethod
    def styled_radiobutton() -> str:
        """RadioButton с улучшенной видимостью - НОВОЕ"""
        return (
            f"QRadioButton {{\n"
            f"    color: {Palette.TEXT_SECONDARY};\n"
            f"    font-family: {Typography.UI};\n"
            f"    font-size: {Typography.SIZE_MD}px;\n"
            f"    spacing: {Spacing.MD}px;\n"
            f"}}\n"
            f"QRadioButton::indicator {{\n"
            f"    width: 20px; height: 20px;\n"
            f"    border: 2px solid {Palette.BORDER_PRIMARY};\n"
            f"    border-radius: 10px;\n"
            f"    background-color: {Palette.BG_DARK_3};\n"
            f"}}\n"
            f"QRadioButton::indicator:hover {{\n"
            f"    border-color: {Palette.PRIMARY};\n"
            f"    background-color: {Palette.with_alpha(Palette.PRIMARY, 0.1)};\n"
            f"}}\n"
            f"QRadioButton::indicator:checked {{\n"
            f"    border: 2px solid {Palette.PRIMARY};\n"
            f"    background-color: {Palette.with_alpha(Palette.PRIMARY, 0.3)};\n"
            f"}}\n"
            f"QRadioButton::indicator:checked:hover {{\n"
            f"    background-color: {Palette.with_alpha(Palette.PRIMARY, 0.5)};\n"
            f"}}\n"
            f"QRadioButton:disabled {{\n"
            f"    color: {Palette.TEXT_MUTED};\n"
            f"}}\n"
            f"QRadioButton::indicator:disabled {{\n"
            f"    background-color: {Palette.BG_DARK};\n"
            f"    border-color: {Palette.BORDER_SOFT};\n"
            f"}}\n"
            f""
        )

    @staticmethod
    def styled_list_widget() -> str:
        return (
            f"QListWidget {{\n"
            f"    background-color: {Palette.BG_DARK_2};\n"
            f"    border: 1px solid {Palette.BORDER_SOFT};\n"
            f"    border-radius: {Spacing.RADIUS_NORMAL}px;\n"
            f"    color: {Palette.TEXT};\n"
            f"    outline: none;\n"
            f"}}\n"
            f"QListWidget::item {{\n"
            f"    padding: {Spacing.XS}px {Spacing.SM}px;\n"
            f"    border-bottom: 2px solid {Palette.with_alpha(Palette.BORDER_SOFT, 0.75)}\n"
            f"}}\n"
            f"QListWidget::item:hover {{\n"
            f"    background-color: {Palette.with_alpha(Palette.TEXT, 0.05)};\n"
            f"}}\n"
            f"QListWidget::item:selected {{\n"
            f"    background-color: {Palette.with_alpha(Palette.PRIMARY, 0.15)};\n"
            f"    color: {Palette.PRIMARY};\n"
            f"    border-left: 2px solid {Palette.PRIMARY};\n"
            f"}}"
        )

    @staticmethod
    def card() -> str:
        return (
            f"QFrame#param_card, QFrame#panel {{\n"
            f"    background-color: {Palette.BG_DARK_2};\n"
            f"    border: 1px solid {Palette.DIVIDER};\n"
            f"    border-radius: {Spacing.RADIUS_NORMAL}px;\n"
            f"}}"
        )
    
    @staticmethod
    def panel() -> str: return Components.card()

    @staticmethod
    def section_title() -> str:
        """Заголовок секции - повышенная видимость"""
        style = Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_LG,
            weight=Typography.WEIGHT_BOLD,
            color=Palette.TEXT,
            letter_spacing=Typography.SPACING_WIDER
        )
        return f"QLabel {{ {style} text-transform: uppercase; }}"

    @staticmethod
    def subsection_title() -> str:
        """Подзаголовок - улучшенная видимость"""
        style = Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_MD,
            weight=Typography.WEIGHT_SEMIBOLD,
            color=Palette.TEXT_SECONDARY,
            letter_spacing=Typography.SPACING_WIDE
        )
        return f"QLabel {{ {style} }}"

    @staticmethod
    def divider() -> str:
        return (
            f"QFrame {{\n"
            f"    background-color: {Palette.DIVIDER};\n"
            f"    min-height: 1px;\n"
            f"    max-height: 1px;\n"
            f"}}"
        )
    
    @staticmethod
    def main_window() -> str:
        return f"QWidget#ParserWidget {{ background-color: {Palette.BG_DARK}; }}"

    @staticmethod
    def nav_button() -> str:
        return (
            f"QPushButton {{\n"
            f"    background: transparent;\n"
            f"    color: {Palette.TEXT_MUTED};\n"
            f"    border: none;\n"
            f"    font-weight: {Typography.WEIGHT_BOLD};\n"
            f"    border-bottom: 2px solid transparent;\n"
            f"    padding: 0 {Spacing.MD}px;\n"
            f"}}\n"
            f"QPushButton:hover {{ color: {Palette.TEXT}; }}\n"
            f"QPushButton:checked {{\n"
            f"    color: {Palette.PRIMARY};\n"
            f"    border-bottom: 2px solid {Palette.PRIMARY};\n"
            f"}}"
        )

    @staticmethod
    def progress_bar(chunk_color: str = Palette.PRIMARY) -> str:
        return (
            f"QProgressBar {{\n"
            f"    border: 1px solid {Palette.BORDER_SOFT};\n"
            f"    background-color: {Palette.BG_DARK_3};\n"
            f"    border-radius: 4px;\n"
            f"    text-align: center;\n"
            f"}}\n"
            f"QProgressBar::chunk {{\n"
            f"    background-color: {chunk_color};\n"
            f"    border-radius: 3px;\n"
            f"}}"
        )

    @staticmethod
    def table() -> str:
        """Таблица с улучшенными эффектами - ЭТАП 4"""
        return (
            f"QTableWidget {{\n"
            f"    background-color: {Palette.BG_DARK_2};\n"
            f"    gridline-color: {Palette.BORDER_PRIMARY};\n"
            f"    border: 1px solid {Palette.BORDER_PRIMARY};\n"
            f"    color: {Palette.TEXT};\n"
            f"    font-family: {Typography.MONO};\n"
            f"    font-size: {Typography.SIZE_MD}px;\n"
            f"    selection-background-color: {Palette.with_alpha(Palette.PRIMARY, 0.3)};\n"
            f"    selection-color: {Palette.TEXT};\n"
            f"    outline: none;\n"
            f"}}\n"
            f"QHeaderView::section {{\n"
            f"    background-color: {Palette.BG_DARK_3};\n"
            f"    color: {Palette.TEXT_SECONDARY};\n"
            f"    border: none;\n"
            f"    border-bottom: 2px solid {Palette.PRIMARY};\n"
            f"    border-right: 1px solid {Palette.BORDER_PRIMARY};\n"
            f"    padding: 6px 8px;\n"
            f"    font-weight: {Typography.WEIGHT_BOLD};\n"
            f"    font-size: {Typography.SIZE_MD}px;\n"
            f"    letter-spacing: {Typography.SPACING_WIDE};\n"
            f"}}\n"
            f"QHeaderView::section:hover {{\n"  # ДОБАВЛЕНО: hover для заголовка
            f"    background-color: {Palette.with_alpha(Palette.SECONDARY, 0.15)};\n"
            f"}}\n"
            f"QTableWidget::item {{\n"
            f"    padding: 4px 6px;\n"
            f"    border-bottom: 1px solid {Palette.with_alpha(Palette.BORDER_SOFT, 0.3)};\n"
            #f"    color: {Palette.TEXT};\n"
            f"}}\n"
            f"QTableWidget::item:hover {{\n"
            f"    background-color: {Palette.with_alpha(Palette.SECONDARY, 0.15)};\n"
            f"}}\n"
            f"QTableWidget::item:selected {{\n"
            f"    background-color: {Palette.with_alpha(Palette.PRIMARY, 0.3)};\n"
            f"    color: {Palette.TEXT};\n"
            f"}}\n"
            f"QScrollBar:vertical {{\n"
            f"    width: 10px;\n"
            f"    background-color: {Palette.BG_DARK_2};\n"
            f"    border-radius: 5px;\n"
            f"}}\n"
            f"QScrollBar::handle:vertical {{\n"
            f"    background-color: {Palette.SECONDARY};\n"
            f"    border-radius: 5px;\n"
            f"    min-height: 20px;\n"
            f"}}\n"
            f"QScrollBar::handle:vertical:hover {{\n"
            f"    background-color: {Palette.SECONDARY_LIGHT};\n"
            f"}}\n"
            f"QScrollBar::up-arrow, QScrollBar::down-arrow {{\n"
            f"    width: 0px;\n"
            f"    height: 0px;\n"
            f"    background: transparent;\n"
            f"    border: none;\n"
            f"}}\n"
            f"QScrollBar::add-line, QScrollBar::sub-line {{\n"
            f"    width: 0px;\n"
            f"    height: 0px;\n"
            f"    background: transparent;\n"
            f"    border: none;\n"
            f"}}\n"
        )

    @staticmethod
    def dialog() -> str:
        return (
            f"QDialog {{ background-color: {Palette.BG_DARK}; }}\n"
            f"QLabel {{ color: {Palette.TEXT}; }}"
        )

class InputComponents:
    @staticmethod
    def text_input() -> str: return Components.text_input()
    
    @staticmethod
    def ai_criteria_input() -> str:
        return (
            f"QPlainTextEdit {{\n"
            f"    background-color: {Palette.with_alpha(Palette.SECONDARY, 0.1)};\n"
            f"    border: 1px solid {Palette.SECONDARY};\n"
            f"    color: {Palette.TEXT};\n"
            f"    border-radius: {Spacing.RADIUS_NORMAL}px;\n"
            f"    padding: {Spacing.XS}px {Spacing.SM}px;\n"
            f"}}\n"
            f"QPlainTextEdit:focus {{\n"
            f"    background-color: {Palette.with_alpha(Palette.SECONDARY, 0.15)};\n"
            f"    border: 1px solid {Palette.SECONDARY_LIGHT};\n"
            f"}}"
        )