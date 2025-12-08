from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QProgressBar, QSizePolicy, QGroupBox
from app.ui.widgets.logger import LogWidget
from app.ui.styles import Components, Palette, Typography, Spacing


class ProgressAndLogsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        main_frame = QFrame()
        main_frame.setObjectName("panel")
        main_frame.setStyleSheet(Components.panel())

        main_layout = QVBoxLayout(main_frame)
        main_layout.setContentsMargins(*Spacing.PADDING_PANEL, *Spacing.PADDING_PANEL)
        main_layout.setSpacing(Spacing.GAP_NORMAL)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)
        content_layout.setSpacing(Spacing.MD)

        left = self._create_column("ПАРСЕР", "")
        self.parser_log = left["log"]
        self.parser_bar = left["bar"]
        content_layout.addWidget(left["frame"], stretch=1)

        right = self._create_column("НЕЙРОСЕТЬ", "")
        self.ai_log = right["log"]
        self.ai_bar = right["bar"]
        content_layout.addWidget(right["frame"], stretch=1)

        main_layout.addLayout(content_layout, stretch=1)

        wrapper = QVBoxLayout(self)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.setSpacing(0)
        wrapper.addWidget(main_frame, stretch=1)

    def _create_column(self, title: str, tooltip: str):
        frame = QFrame()
        frame.setStyleSheet("border: none;")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)

        lbl = QLabel(title)
        lbl.setStyleSheet(Components.section_title())
        layout.addWidget(lbl)

        log = LogWidget()
        log.setMinimumHeight(80)
        log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(log, stretch=1)

        bar = QProgressBar()
        bar.setFixedHeight(8)
        bar.setTextVisible(False)
        bar.setToolTip(tooltip)
        bar.setStyleSheet(Components.progress_bar())
        layout.addWidget(bar)

        return {"frame": frame, "layout": layout, "log": log, "bar": bar}