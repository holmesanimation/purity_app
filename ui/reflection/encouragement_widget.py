from PySide6.QtWidgets import QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt
from ui.widgets.card import CardWidget
from styles.theme import (
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_ACCENT,
    FONT_FAMILY, FONT_SIZE_SMALL, FONT_SIZE_NORMAL, FONT_SIZE_MEDIUM,
)

_VERSES = [
    {
        "reference": "Philippians 4:13",
        "text": "I can do all things through Christ who strengthens me.",
    },
    {
        "reference": "Galatians 5:16",
        "text": "Walk by the Spirit, and you will not gratify the desires of the flesh.",
    },
    {
        "reference": "1 Corinthians 10:13",
        "text": (
            "No temptation has overtaken you that is not common to man. "
            "God is faithful, and he will not let you be tempted beyond your ability."
        ),
    },
    {
        "reference": "Romans 8:37",
        "text": "In all these things we are more than conquerors through him who loved us.",
    },
    {
        "reference": "Psalm 119:9",
        "text": "How can a young man keep his way pure? By guarding it according to your word.",
    },
    {
        "reference": "2 Timothy 2:22",
        "text": "Flee youthful passions and pursue righteousness, faith, love, and peace.",
    },
]


class EncouragementWidget(CardWidget):
    def __init__(self, parent=None):
        super().__init__("Daily Word", parent)
        self._index = 0
        self._build()

    def _build(self):
        self._ref_lbl = QLabel()
        self._ref_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_SMALL}pt;"
            f"color: {COLOR_TEXT_MUTED}; background: transparent;"
        )
        self._ref_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body_layout.addWidget(self._ref_lbl)

        self._verse_lbl = QLabel()
        self._verse_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL}pt;"
            f"font-style: italic; color: {COLOR_TEXT}; background: transparent;"
        )
        self._verse_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._verse_lbl.setWordWrap(True)
        self.body_layout.addWidget(self._verse_lbl)

        self._insight_lbl = QLabel("You are not fighting alone. Keep going.")
        self._insight_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_SMALL}pt;"
            f"color: {COLOR_ACCENT}; background: transparent;"
        )
        self._insight_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._insight_lbl.setWordWrap(True)
        self.body_layout.addWidget(self._insight_lbl)

        new_verse_btn = QPushButton("New verse")
        new_verse_btn.setFixedWidth(120)
        new_verse_btn.setProperty("flat", "true")
        new_verse_btn.setStyleSheet(
            f"background-color: transparent; color: {COLOR_TEXT_MUTED};"
            f"border: 1px solid #DDD8CF; border-radius: 6px; padding: 4px 10px;"
            f"font-size: {FONT_SIZE_SMALL}pt;"
        )
        new_verse_btn.clicked.connect(self._next_verse)
        self.body_layout.addWidget(new_verse_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self._refresh()

    def _refresh(self):
        verse = _VERSES[self._index % len(_VERSES)]
        self._ref_lbl.setText(verse["reference"])
        self._verse_lbl.setText(f'"{verse["text"]}"')

    def _next_verse(self):
        self._index += 1
        self._refresh()
