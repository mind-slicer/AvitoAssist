"""
Unified styling system for Avito Parser
Modular, reusable, and maintainable CSS-in-Python
"""
from .palette import Palette
from .spacing import Spacing
from .typography import Typography
from .components import Components, InputComponents

# ============ Backward compatibility ============
# These are imported by existing code: `from app import styles`

# Colors (legacy names)
COLOR_BG_DARK = Palette.BG_DARK
COLOR_BG_DARK_2 = Palette.BG_DARK_2
COLOR_BG_DARK_3 = Palette.BG_DARK_3
COLOR_BG_PANEL = Palette.BG_OVERLAY
COLOR_PRIMARY = Palette.PRIMARY
COLOR_PRIMARY_SOFT = Palette.PRIMARY_LIGHT
COLOR_PRIMARY_SOFT_BORDER = Palette.BORDER_SOFT
COLOR_ACCENT_PURPLE = Palette.SECONDARY
COLOR_TEXT = Palette.TEXT
COLOR_TEXT_MUTED = Palette.TEXT_MUTED
COLOR_BORDER_SOFT = Palette.BORDER_SOFT

# Typography (legacy names)
FONT_MONO = Typography.MONO
FONT_UI = Typography.UI

# Pre-built component styles (legacy names)
# NOTE: These legacy styles have been removed in the refactoring.
# Please update your code to use the new Components API directly.
MAIN_WINDOW_STYLE = Components.main_window()
NAV_BTN_STYLE = Components.nav_button()
TABLE_STYLE = Components.table()

# The following legacy styles have been removed:
# GROUP_BOX_STYLE = Components.group_box()
# CLEAR_BTN_STYLE = Components.ghost_button()
# START_BTN_STYLE = Components.start_button()
# STOP_BTN_STYLE = Components.stop_button()
# TAGS_TOOLBAR_BTN_STYLE = Components.icon_button()
# DIALOG_STYLE = Components.dialog()

# ============ New API ============
__all__ = [
    # Modules
    'Palette', 'Spacing', 'Typography', 'Components', 'InputComponents',
    # Legacy exports (for backward compatibility)
    'COLOR_BG_DARK', 'COLOR_BG_DARK_2', 'COLOR_BG_DARK_3', 'COLOR_BG_PANEL',
    'COLOR_PRIMARY', 'COLOR_PRIMARY_SOFT', 'COLOR_PRIMARY_SOFT_BORDER', 'COLOR_ACCENT_PURPLE',
    'COLOR_TEXT', 'COLOR_TEXT_MUTED', 'COLOR_BORDER_SOFT',
    'FONT_MONO', 'FONT_UI',
    # Only the remaining legacy styles that still exist
    'MAIN_WINDOW_STYLE', 'NAV_BTN_STYLE', 'TABLE_STYLE'
]