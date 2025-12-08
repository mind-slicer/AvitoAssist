# app/ui/styles/spacing.py

from PyQt6.QtWidgets import QVBoxLayout

class Spacing:
    """
    Единая система расстояний (8px grid).
    Использование: layout.setSpacing(Spacing.MD)
    """
    
    # Base units (8px grid)
    XS = 4       # 4px - микро
    SM = 8       # 8px - маленькое
    MD = 12      # 12px - среднее (DEFAULT)
    LG = 16      # 16px - большое
    XL = 24      # 24px - огромное
    XXL = 32     # 32px - гигантское
    
    # Специфичные отступы
    PADDING_BUTTON = (10, 18)
    PADDING_INPUT = (8, 14)
    PADDING_CARD = (14, 14)
    PADDING_PANEL = (12, 12)
    PADDING_MODAL = (18, 18)
    
    # Зазоры между элементами
    GAP_TIGHT = 6
    GAP_NORMAL = 10
    GAP_ADAPTIVE = 12
    GAP_LOOSE = 14
    GAP_SECTION = 20
    GAP_PAGE = 28
    
    # Скругления
    RADIUS_SHARP = 2    # Острые углы
    RADIUS_NORMAL = 6   # Обычные (DEFAULT)
    RADIUS_SMOOTH = 8   # Гладкие
    RADIUS_PILL = 24    # Таблетка

    # ✨ ИСПОЛЬЗОВАНИЕ:
    @staticmethod
    def example_layout():
        layout = QVBoxLayout()
        layout.setContentsMargins(*Spacing.PADDING_PANEL, *Spacing.PADDING_PANEL)
        layout.setSpacing(Spacing.GAP_ADAPTIVE)
        return layout