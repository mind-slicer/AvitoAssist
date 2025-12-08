# app/ui/styles/palette.py

class Palette:
    """
    Единая цветовая палитра.
    """
    
    # ============ ФОНЫ ============
    BG_DARK = "#1a1a1a"        # Основной фон окна
    BG_DARK_2 = "#242424"      # Панели, карточки
    BG_DARK_3 = "#2d2d2d"      # Контейнеры, input фон
    BG_LIGHT = "#363636"       # Поля ввода, hover
    BG_OVERLAY = "#000000"     # Модали (с alpha)
    
    # ============ PRIMARY (ОРАНЖЕВЫЙ) ============
    PRIMARY = "#ff8c42"        # Main color
    PRIMARY_DARK = "#e07030"   # Hover
    PRIMARY_LIGHT = "#ffaa6b"  # Focus
    
    # ============ SECONDARY (ТЕМНО-СЕРЫЙ - ИЗМЕНЕН) ============
    SECONDARY = "#4a4a4a"
    SECONDARY_DARK = "#3a3a3a"
    SECONDARY_LIGHT = "#5a5a5a"
    
    # ============ TERTIARY (ГОЛУБОЙ) ============
    TERTIARY = "#4da6ff"       
    
    # ============ ТЕКСТ ============
    TEXT = "#f0f0f0"
    TEXT_ON_PRIMARY = "#1a1a1a"
    TEXT_SECONDARY = "#e0e0e0" 
    TEXT_MUTED = "#b8b8b8"     
    
    # ============ ГРАНИЦЫ ============
    BORDER_PRIMARY = "#404040"     
    BORDER_SOFT = "#333333"        
    BORDER_FOCUS = PRIMARY         
    DIVIDER = "#404040"            
    
    # ============ СЕМАНТИЧЕСКИЕ ============
    SUCCESS = "#52c41a"        
    WARNING = "#ff9800"      
    ERROR = "#ff4d4f"          
    INFO = TERTIARY            

    @staticmethod
    def with_alpha(hex_color: str, alpha: float) -> str:
        hex_color = hex_color.lstrip('#')
        if len(hex_color) == 3:
            hex_color = ''.join([c*2 for c in hex_color])
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return f"rgba({r}, {g}, {b}, {alpha})"