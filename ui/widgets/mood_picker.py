from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PySide6.QtCore import Signal
from styles.theme import COLOR_SURFACE_2, COLOR_BORDER, COLOR_ACCENT, FONT_SIZE_LARGE


_MOODS = ["😊", "😐", "😞", "😣"]


class MoodPicker(QWidget):
    """Row of emoji mood buttons. Emits mood_selected(str) when one is clicked."""

    mood_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._buttons: dict[str, QPushButton] = {}
        for mood in _MOODS:
            btn = QPushButton(mood)
            btn.setFixedSize(44, 44)
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  background-color: {COLOR_SURFACE_2};"
                f"  border: 1px solid {COLOR_BORDER};"
                f"  border-radius: 22px;"
                f"  font-size: {FONT_SIZE_LARGE}pt;"
                f"  color: black;"
                f"}}"
                f"QPushButton:hover {{"
                f"  border: 2px solid {COLOR_ACCENT};"
                f"}}"
                f"QPushButton:checked {{"
                f"  border: 2px solid {COLOR_ACCENT};"
                f"  background-color: white;"
                f"}}"
            )
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, m=mood: self._on_click(m))
            layout.addWidget(btn)
            self._buttons[mood] = btn

        layout.addStretch()

    def _on_click(self, mood: str):
        for m, btn in self._buttons.items():
            btn.setChecked(m == mood)
        self.mood_selected.emit(mood)

    def selected_mood(self) -> str:
        for mood, btn in self._buttons.items():
            if btn.isChecked():
                return mood
        return ""
