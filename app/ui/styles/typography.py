# app/ui/styles/typography.py

from .palette import Palette

class Typography:
    """
    Typography constants and utilities.
    Includes font families, sizes, weights, line heights, and letter spacing.
    """
    # ============ FONT FAMILIES ============
    MONO = "'Consolas', 'Monaco', 'Courier New', monospace"
    UI = "'Segoe UI', 'Roboto', 'Arial', sans-serif"
    SERIF = "'Georgia', 'Garamond', serif"
    SYSTEM = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    
    # ============ FONT SIZES (in pixels) ============
    SIZE_XS = 8
    SIZE_SM = 10
    SIZE_MD = 12      # Base size
    SIZE_LG = 14
    SIZE_XL = 16
    SIZE_2XL = 18
    SIZE_3XL = 20
    
    # ============ FONT WEIGHTS ============
    WEIGHT_THIN = "100"
    WEIGHT_LIGHT = "300"
    WEIGHT_NORMAL = "400"
    WEIGHT_MEDIUM = "500"
    WEIGHT_SEMIBOLD = "600"
    WEIGHT_BOLD = "700"
    WEIGHT_EXTRABOLD = "800"
    
    # ============ LINE HEIGHTS ============
    LINE_TIGHT = "1"
    LINE_NORMAL = "1.5"
    LINE_RELAXED = "1.75"
    LINE_LOOSE = "2"
    
    # ============ LETTER SPACING ============
    SPACING_TIGHT = "-0.5px"
    SPACING_NORMAL = "0px"
    SPACING_WIDE = "0.5px"
    SPACING_WIDER = "1px"
    SPACING_WIDEST = "2px"
    
    # -------- Legacy aliases (backward compatibility) --------
    SIZE_TINY = SIZE_XS
    SIZE_SMALL = SIZE_SM
    SIZE_NORMAL = SIZE_MD
    SIZE_LARGE = SIZE_LG
    SIZE_MEDIUM = SIZE_MD
    
    @staticmethod
    def style(
        family: str = None,
        size: int = None,
        weight: str = None,
        color: str = None,
        line_height: str = None,
        letter_spacing: str = None
    ) -> str:
        """
        Generate font style string from individual properties.
        Args:
            family: Font family (e.g., Typography.MONO or Typography.UI)
            size: Font size in pixels
            weight: Font weight (e.g., Typography.WEIGHT_BOLD)
            color: Text color (hex or named)
            line_height: Line height (e.g., "1.5" or "20px")
            letter_spacing: Letter spacing (e.g., "0.5px")
        Returns:
            CSS style string
        Example:
            >>> Typography.style(
            ...     family=Typography.MONO,
            ...     size=12,
            ...     weight=Typography.WEIGHT_BOLD,
            ...     color=Palette.TEXT
            ... )
            'font-family: ...; font-size: 12px; ...'
        """
        parts = []
        if family:
            parts.append(f"font-family: {family}")
        if size:
            parts.append(f"font-size: {size}px")
        if weight:
            parts.append(f"font-weight: {weight}")
        if color:
            parts.append(f"color: {color}")
        if line_height:
            parts.append(f"line-height: {line_height}")
        if letter_spacing:
            parts.append(f"letter-spacing: {letter_spacing}")
        return "; ".join(parts) + ";" if parts else ""

class TextPresets:
    """
    Pre-defined text styles for common use cases.
    Covers headings, body, buttons, inputs, code, labels, and messages.
    """
    # ============ HEADINGS ============
    @staticmethod
    def h1() -> str:
        """Large heading (20px, bold, UI family)"""
        return Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_3XL,
            weight=Typography.WEIGHT_BOLD,
            line_height=Typography.LINE_TIGHT,
            color=Palette.TEXT
        )
    
    @staticmethod
    def h2() -> str:
        """Medium heading (18px, bold, UI family)"""
        return Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_2XL,
            weight=Typography.WEIGHT_BOLD,
            line_height=Typography.LINE_TIGHT,
            color=Palette.TEXT
        )
    
    @staticmethod
    def h3() -> str:
        """Small heading (16px, semibold, UI family)"""
        return Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_XL,
            weight=Typography.WEIGHT_SEMIBOLD,
            line_height=Typography.LINE_TIGHT,
            color=Palette.TEXT
        )
    
    # ============ BODY TEXT ============
    @staticmethod
    def body() -> str:
        """Regular body text (12px, normal, UI family)"""
        return Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_MD,
            weight=Typography.WEIGHT_NORMAL,
            line_height=Typography.LINE_NORMAL,
            color=Palette.TEXT
        )
    
    @staticmethod
    def body_small() -> str:
        """Small body text (10px, normal, UI family)"""
        return Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_SM,
            weight=Typography.WEIGHT_NORMAL,
            line_height=Typography.LINE_NORMAL,
            color=Palette.TEXT_SECONDARY
        )
    
    @staticmethod
    def body_large() -> str:
        """Large body text (14px, normal, UI family)"""
        return Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_LG,
            weight=Typography.WEIGHT_NORMAL,
            line_height=Typography.LINE_NORMAL,
            color=Palette.TEXT
        )
    
    # ============ BUTTON TEXT ============
    @staticmethod
    def button() -> str:
        """Button text (12px, medium, UI family, wide spacing)"""
        return Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_MD,
            weight=Typography.WEIGHT_MEDIUM,
            letter_spacing=Typography.SPACING_WIDE,
            line_height=Typography.LINE_TIGHT,
            color=Palette.TEXT
        )
    
    @staticmethod
    def button_small() -> str:
        """Small button text (10px, medium)"""
        return Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_SM,
            weight=Typography.WEIGHT_MEDIUM,
            letter_spacing=Typography.SPACING_WIDE,
            color=Palette.TEXT_SECONDARY
        )
    
    @staticmethod
    def button_large() -> str:
        """Large button text (14px, semibold)"""
        return Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_LG,
            weight=Typography.WEIGHT_SEMIBOLD,
            letter_spacing=Typography.SPACING_WIDE,
            color=Palette.TEXT
        )
    
    # ============ INPUT TEXT ============
    @staticmethod
    def input() -> str:
        """Input field text (12px, normal)"""
        return Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_MD,
            weight=Typography.WEIGHT_NORMAL,
            color=Palette.TEXT
        )
    
    @staticmethod
    def input_small() -> str:
        """Small input field text (10px)"""
        return Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_SM,
            weight=Typography.WEIGHT_NORMAL,
            color=Palette.TEXT_SECONDARY
        )
    
    @staticmethod
    def input_placeholder() -> str:
        """Input placeholder text (10px, muted)"""
        return Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_SM,
            weight=Typography.WEIGHT_NORMAL,
            color=Palette.TEXT_MUTED
        )
    
    # ============ CODE TEXT ============
    @staticmethod
    def code() -> str:
        """Code/monospace text (11px, mono family)"""
        return Typography.style(
            family=Typography.MONO,
            size=Typography.SIZE_MD,
            weight=Typography.WEIGHT_NORMAL,
            line_height=Typography.LINE_NORMAL,
            color=Palette.TEXT
        )
    
    @staticmethod
    def code_small() -> str:
        """Small code text (9px, mono)"""
        return Typography.style(
            family=Typography.MONO,
            size=Typography.SIZE_XS,
            weight=Typography.WEIGHT_NORMAL,
            color=Palette.TEXT_MUTED
        )
    
    @staticmethod
    def code_large() -> str:
        """Large code text (13px, mono)"""
        return Typography.style(
            family=Typography.MONO,
            size=Typography.SIZE_LG,
            weight=Typography.WEIGHT_NORMAL,
            color=Palette.TEXT
        )
    
    # ============ LABELS ============
    @staticmethod
    def label() -> str:
        """Label text (10px, bold, mono, wide spacing, uppercase)"""
        return Typography.style(
            family=Typography.MONO,
            size=Typography.SIZE_MD,
            weight=Typography.WEIGHT_BOLD,
            letter_spacing=Typography.SPACING_NORMAL,
            line_height=Typography.LINE_TIGHT,
            color=Palette.TEXT_SECONDARY
        ) + " text-transform: uppercase;"
    
    @staticmethod
    def label_small() -> str:
        """Small label (8px, bold, uppercase)"""
        return Typography.style(
            family=Typography.MONO,
            size=Typography.SIZE_MD,
            weight=Typography.WEIGHT_BOLD,
            letter_spacing=Typography.SPACING_WIDEST,
            color=Palette.TEXT_MUTED
        ) + " text-transform: uppercase;"
    
    # ============ MESSAGES ============
    @staticmethod
    def hint() -> str:
        """Hint/help text (9px, light, muted)"""
        return Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_XS,
            weight=Typography.WEIGHT_LIGHT,
            color=Palette.TEXT_MUTED
        )
    
    @staticmethod
    def error() -> str:
        """Error message text (10px, semibold, red)"""
        return Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_SM,
            weight=Typography.WEIGHT_SEMIBOLD,
            color=Palette.ERROR
        )
    
    @staticmethod
    def success() -> str:
        """Success message text (10px, semibold, green)"""
        return Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_SM,
            weight=Typography.WEIGHT_SEMIBOLD,
            color=Palette.SUCCESS
        )
    
    @staticmethod
    def warning() -> str:
        """Warning message text (10px, semibold, orange)"""
        return Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_SM,
            weight=Typography.WEIGHT_SEMIBOLD,
            color=Palette.WARNING
        )
    
    @staticmethod
    def info() -> str:
        """Info message text (10px, semibold, cyan)"""
        return Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_SM,
            weight=Typography.WEIGHT_SEMIBOLD,
            color=Palette.INFO
        )
    
    # ============ TABLE/LIST ============
    @staticmethod
    def table_header() -> str:
        """Table header text (10px, bold, uppercase, wide spacing)"""
        return Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_MD,
            weight=Typography.WEIGHT_BOLD,
            letter_spacing=Typography.SPACING_NORMAL,
            color=Palette.TEXT_SECONDARY
        ) + " text-transform: uppercase;"
    
    @staticmethod
    def table_cell() -> str:
        """Table cell text (11px, normal)"""
        return Typography.style(
            family=Typography.MONO,
            size=Typography.SIZE_MD,
            weight=Typography.WEIGHT_NORMAL,
            color=Palette.TEXT
        )
    
    @staticmethod
    def list_item() -> str:
        """List item text (12px, normal)"""
        return Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_MD,
            weight=Typography.WEIGHT_NORMAL,
            line_height=Typography.LINE_RELAXED,
            color=Palette.TEXT
        )
    
    # ============ SPECIAL ============
    @staticmethod
    def badge() -> str:
        """Badge text (8px, bold, uppercase)"""
        return Typography.style(
            family=Typography.MONO,
            size=Typography.SIZE_XS,
            weight=Typography.WEIGHT_BOLD,
            letter_spacing=Typography.SPACING_WIDEST,
            color=Palette.TEXT
        ) + " text-transform: uppercase;"
    
    @staticmethod
    def caption() -> str:
        """Caption text (9px, light)"""
        return Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_XS,
            weight=Typography.WEIGHT_LIGHT,
            line_height=Typography.LINE_TIGHT,
            color=Palette.TEXT_MUTED
        )