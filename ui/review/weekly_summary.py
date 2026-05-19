from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt
from services.fake_ai import FakeAIService
from services.mock_state import MockAppState
from ui.widgets.stat_row import StatRow
from ui.widgets.section_header import SectionHeader
from styles.theme import (
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_SURFACE_2, COLOR_BORDER,
    FONT_FAMILY, FONT_SIZE_SMALL, FONT_SIZE_NORMAL,
)


class WeeklySummaryWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        state = MockAppState()
        ai = FakeAIService()
        self._build(state, ai)

    def _build(self, state: MockAppState, ai: FakeAIService):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # ── Summary stats row ─────────────────────────────────
        layout.addWidget(SectionHeader("This Week at a Glance"))

        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        for label, value, status in [
            ("Clean Days",      "6 / 7",  "good"),
            ("Journal Entries", "5",      "normal"),
            ("Prayer Sessions", "9",      "good"),
        ]:
            stats_row.addWidget(StatRow(label, value, status))
        layout.addLayout(stats_row)

        # ── Top themes ────────────────────────────────────────
        layout.addWidget(SectionHeader("Top Trigger Themes"))

        for category, count in ai.get_categories():
            row = QHBoxLayout()
            cat_lbl = QLabel(f"• {category}")
            cat_lbl.setStyleSheet(
                f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
                f"font-size: {FONT_SIZE_NORMAL}pt; background: transparent;"
            )
            count_lbl = QLabel(f"{count}×")
            count_lbl.setStyleSheet(
                f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
                f"font-size: {FONT_SIZE_SMALL}pt; background: transparent;"
            )
            row.addWidget(cat_lbl)
            row.addStretch()
            row.addWidget(count_lbl)
            layout.addLayout(row)

        # ── AI reflection paragraph ───────────────────────────
        layout.addWidget(SectionHeader("Reflection"))

        reflection_lbl = QLabel(ai.get_weekly_report())
        reflection_lbl.setWordWrap(True)
        reflection_lbl.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_NORMAL}pt; font-style: italic;"
            f"background: {COLOR_SURFACE_2}; border-radius: 6px; padding: 10px;"
        )
        layout.addWidget(reflection_lbl)
