from PySide6.QtWidgets import QCheckBox
from ui.widgets.card import CardWidget
from services.mock_state import MockAppState
from styles.theme import COLOR_TEXT, FONT_FAMILY, FONT_SIZE_NORMAL


class GoalsWidget(CardWidget):
    def __init__(self, state: MockAppState, parent=None):
        super().__init__("Today's Goals", parent)
        self._state = state
        self._build()

    def _build(self):
        for goal in self._state.goals:
            cb = QCheckBox(goal.title)
            cb.setChecked(goal.completed_today)
            cb.setStyleSheet(
                f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL}pt;"
                f"color: {COLOR_TEXT};"
            )
            # Capture goal_id by value in the lambda default arg
            cb.toggled.connect(
                lambda checked, gid=goal.id: self._state.set_goal_completed(gid, checked)
            )
            self.body_layout.addWidget(cb)
