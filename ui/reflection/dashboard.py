from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QScrollArea, QLabel, QFrame,
)
from PySide6.QtCore import Qt
from services.mock_state import MockAppState
from services.fake_journal import FakeJournalService
from services.fake_prayer import FakePrayerService
from ui.reflection.streak_widget import StreakWidget
from ui.reflection.health_widget import HealthWidget
from ui.reflection.goals_widget import GoalsWidget
from ui.reflection.journal_panel import JournalPanel
from ui.reflection.encouragement_widget import EncouragementWidget
from ui.reflection.prayer_widget import PrayerWidget
from ui.widgets.card import CardWidget
from styles.theme import (
    COLOR_BACKGROUND, COLOR_TEXT_MUTED, COLOR_WARNING, COLOR_DANGER,
    FONT_FAMILY, FONT_SIZE_SMALL,
)


def _make_scroll_column(contents: list[QWidget], min_width: int = 260) -> QScrollArea:
    """Wrap a list of widgets in a vertical scroll area column."""
    container = QWidget()
    container.setProperty("class", "transparent")
    vbox = QVBoxLayout(container)
    vbox.setContentsMargins(8, 8, 8, 8)
    vbox.setSpacing(12)
    for w in contents:
        vbox.addWidget(w)
    vbox.addStretch()

    scroll = QScrollArea()
    scroll.setProperty("class", "transparent")
    scroll.setWidgetResizable(True)
    scroll.setWidget(container)
    scroll.setMinimumWidth(min_width)
    scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    return scroll


def _build_risk_card(state: MockAppState) -> CardWidget:
    risk_labels = {
        "low":    ("🟢 Low Risk",    "You're in a strong place. Keep your commitments."),
        "medium": ("⚠️ Caution",     "Fatigue and stress are elevated. Stay anchored."),
        "high":   ("🔴 High Risk",   "Multiple risk factors active. Reach out to someone."),
    }
    label, desc = risk_labels.get(state.risk_level, risk_labels["low"])
    card = CardWidget("Risk Assessment")
    lbl = QLabel(label)
    lbl.setStyleSheet(
        f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_SMALL + 1}pt;"
        f"font-weight: 700; background: transparent;"
        f"color: {'#A83232' if state.risk_level == 'high' else '#C47C2B' if state.risk_level == 'medium' else '#4A7C59'};"
    )
    desc_lbl = QLabel(desc)
    desc_lbl.setWordWrap(True)
    desc_lbl.setStyleSheet(
        f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_SMALL}pt;"
        f"color: {COLOR_TEXT_MUTED}; background: transparent;"
    )
    card.body_layout.addWidget(lbl)
    card.body_layout.addWidget(desc_lbl)
    return card


class ReflectionDashboard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "transparent")

        state = MockAppState()
        journal_svc = FakeJournalService()
        prayer_svc = FakePrayerService()

        # ── Left column: streak + health + goals ──────────────────
        left_col = _make_scroll_column([
            StreakWidget(state),
            HealthWidget(state),
            GoalsWidget(state),
        ], min_width=260)

        # ── Center column: journal + encouragement ────────────────
        center_col = _make_scroll_column([
            JournalPanel(journal_svc),
            EncouragementWidget(),
        ], min_width=340)

        # ── Right column: prayer + risk ───────────────────────────
        right_col = _make_scroll_column([
            PrayerWidget(prayer_svc),
            _build_risk_card(state),
        ], min_width=260)

        # ── Assemble ──────────────────────────────────────────────
        hbox = QHBoxLayout(self)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(0)
        hbox.addWidget(left_col, stretch=1)
        hbox.addWidget(center_col, stretch=2)
        hbox.addWidget(right_col, stretch=1)
