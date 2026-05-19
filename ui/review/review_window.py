from datetime import date, timedelta
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QApplication
from services.fake_ai import FakeAIService
from ui.review.weekly_summary import WeeklySummaryWidget
from ui.review.trend_cards import TrendCardsWidget
from ui.widgets.section_header import SectionHeader
from styles.theme import (
    COLOR_BACKGROUND, COLOR_BORDER, COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_ACCENT,
    FONT_FAMILY, FONT_SIZE_TITLE, FONT_SIZE_SMALL, FONT_SIZE_NORMAL,
)


class ReviewWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Weekly Review")
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowTitleHint
        )
        self.setModal(False)
        self.resize(760, 680)
        self._build()
        self._center_on_screen()

    def _build(self):
        ai = FakeAIService()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Scrollable body ───────────────────────────────────
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body = QWidget()
        body.setStyleSheet(f"background-color: {COLOR_BACKGROUND};")
        vbox = QVBoxLayout(body)
        vbox.setContentsMargins(28, 24, 28, 24)
        vbox.setSpacing(20)

        # Header — date range
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end   = week_start + timedelta(days=6)
        date_range = f"{week_start.strftime('%B %d')} – {week_end.strftime('%B %d, %Y')}"

        title_lbl = QLabel("Weekly Review")
        title_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_TITLE}pt;"
            f"font-weight: 800; color: {COLOR_TEXT}; background: transparent;"
        )
        vbox.addWidget(title_lbl)

        date_lbl = QLabel(date_range)
        date_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_NORMAL}pt; background: transparent;"
        )
        vbox.addWidget(date_lbl)

        # Trend cards
        vbox.addWidget(SectionHeader("Trends"))
        vbox.addWidget(TrendCardsWidget())

        # Weekly summary
        vbox.addWidget(WeeklySummaryWidget())

        # Suggestions
        vbox.addWidget(SectionHeader("Suggested Focus Areas"))
        for suggestion in ai.get_suggestions():
            lbl = QLabel(f"→  {suggestion}")
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
                f"font-size: {FONT_SIZE_NORMAL}pt; background: transparent; padding: 2px 0;"
            )
            vbox.addWidget(lbl)

        # Encouragement
        encouragement = ai.get_encouragement_insight()
        enc_lbl = QLabel(f'"{encouragement}"')
        enc_lbl.setWordWrap(True)
        enc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        enc_lbl.setStyleSheet(
            f"color: {COLOR_ACCENT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_NORMAL}pt; font-style: italic;"
            f"background: transparent; padding: 8px 0;"
        )
        vbox.addWidget(enc_lbl)

        vbox.addStretch()
        scroll_area.setWidget(body)
        outer.addWidget(scroll_area)

        # ── Footer with Close button ──────────────────────────
        footer = QWidget()
        footer.setStyleSheet(
            f"background-color: {COLOR_BACKGROUND};"
            f"border-top: 1px solid {COLOR_BORDER};"
        )
        footer_row = QHBoxLayout(footer)
        footer_row.setContentsMargins(24, 10, 24, 10)

        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        footer_row.addStretch()
        footer_row.addWidget(close_btn)

        outer.addWidget(footer)

    def _center_on_screen(self):
        screen: QScreen = QApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width()  - self.width())  // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        self.move(x, y)
