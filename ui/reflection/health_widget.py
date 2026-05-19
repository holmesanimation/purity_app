from PySide6.QtWidgets import QVBoxLayout
from ui.widgets.card import CardWidget
from ui.widgets.stat_row import StatRow
from services.mock_state import MockAppState
from styles.theme import COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER


def _sleep_status(hours: float) -> str:
    if hours >= 7:
        return "good"
    if hours >= 5:
        return "warning"
    return "danger"


def _hydration_status(glasses: int, target: int) -> str:
    ratio = glasses / target if target else 0
    if ratio >= 0.75:
        return "good"
    if ratio >= 0.5:
        return "warning"
    return "danger"


def _protein_status(actual: int, target: int) -> str:
    ratio = actual / target if target else 0
    if ratio >= 0.8:
        return "good"
    if ratio >= 0.5:
        return "warning"
    return "danger"


def _caffeine_status(cups: int) -> str:
    if cups <= 2:
        return "good"
    if cups <= 4:
        return "warning"
    return "danger"


class HealthWidget(CardWidget):
    def __init__(self, state: MockAppState, parent=None):
        super().__init__("Health Today", parent)
        self._state = state
        self._build()

    def _build(self):
        h = self._state.health

        self.body_layout.addWidget(StatRow(
            "Sleep",
            f"{h.sleep_hours}h",
            _sleep_status(h.sleep_hours),
        ))
        self.body_layout.addWidget(StatRow(
            "Hydration",
            f"{h.hydration_glasses}/{h.hydration_target} glasses",
            _hydration_status(h.hydration_glasses, h.hydration_target),
        ))
        self.body_layout.addWidget(StatRow(
            "Workout",
            "Done ✓" if h.workout_done else "Not yet",
            "good" if h.workout_done else "warning",
        ))
        self.body_layout.addWidget(StatRow(
            "Protein",
            f"{h.protein_g}/{h.protein_target}g",
            _protein_status(h.protein_g, h.protein_target),
        ))
        self.body_layout.addWidget(StatRow(
            "Caffeine",
            f"{h.caffeine_cups} cup{'s' if h.caffeine_cups != 1 else ''}",
            _caffeine_status(h.caffeine_cups),
        ))
