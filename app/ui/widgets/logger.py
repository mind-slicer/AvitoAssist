from PyQt6.QtWidgets import QPlainTextEdit
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor
from app.ui.styles import Palette, Typography, Spacing

class LogWidget(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setUndoRedoEnabled(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMaximumBlockCount(2000)
        
        # FIX: Added placeholder text
        self.setPlaceholderText("РћР¶РёРґР°РЅРёРµ СЃРѕР±С‹С‚РёР№...")
        
        self._apply_style()
        self.clear()
        
    def _apply_style(self):
        # FIX: Slightly lighter background to differentiate from disabled state
        box_style = (
            f"background-color: {Palette.BG_DARK_2}; " 
            f"border: 1px solid {Palette.BORDER_SOFT}; "
            f"border-radius: {Spacing.RADIUS_NORMAL}px; "
            f"padding: {Spacing.XS}px; "
        )
        text_style = Typography.style(
            family=Typography.MONO,
            size=Typography.SIZE_MD,
            weight=Typography.WEIGHT_NORMAL,
            color=Palette.TEXT_MUTED,
        )
        self.setStyleSheet(box_style + " " + text_style)

    def _append_line(self, msg: str):
        if not msg: return
        self.appendPlainText(msg)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)

    def info(self, msg: str): self._append_line(msg)
    def success(self, msg: str): self._append_line(f"[OK] {msg}")
    def warning(self, msg: str): self._append_line(f"[WARN] {msg}")
    def error(self, msg: str): self._append_line(f"[ERR] {msg}")
    def progress(self, msg: str): self._append_line(msg)
    def ai_status(self, msg: str): self._append_line(f"[AI] {msg}")