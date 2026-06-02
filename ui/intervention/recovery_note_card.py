"""Small always-on-top recovery note card.

Floats beside the panic reason dialog when the user selects a reason button.
Shows a brief encouragement phrase and scripture tuned for that reason.

Each card emits ``dismissed(reason_id)`` when closed via the × button,
which allows the reason dialog to deselect the corresponding button.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from styles.theme import (
    COLOR_ACCENT,
    COLOR_ACCENT_DARK,
    COLOR_BORDER,
    COLOR_SURFACE,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    FONT_FAMILY,
    FONT_SIZE_NORMAL,
    FONT_SIZE_SMALL,
)

# ---------------------------------------------------------------------------
# Per-reason card content: (short encouragement, verse_ref, verse_short)
# Kept compact to fit the card dimensions.
# ---------------------------------------------------------------------------

REASON_CARD_CONTENT: dict[str, tuple[str, str, str]] = {
    "home_alone": (
        "You are never truly alone.",
        "Deut. 31:6",
        "\"He will never leave you nor forsake you.\"",
    ),
    "triggering_content": (
        "You can turn away. That choice is strength.",
        "2 Tim. 2:22",
        "\"Flee youthful passions and pursue righteousness.\"",
    ),
    "tired": (
        "Rest is a gift, not a weakness.",
        "Matt. 11:28",
        "\"Come to me… and I will give you rest.\"",
    ),
    "hungry": (
        "Take care of your body — it is a gift.",
        "Matt. 4:4",
        "\"Man shall not live by bread alone.\"",
    ),
    "biological_urge": (
        "The urge is not a command. You have more power than it.",
        "1 Cor. 10:13",
        "\"God will not let you be tempted beyond what you can bear.\"",
    ),
    "lonely": (
        "Loneliness is real — and God sees it.",
        "Ps. 34:18",
        "\"The Lord is near to the brokenhearted.\"",
    ),
    "discouraged": (
        "Discouragement is not the final word.",
        "Phil. 4:6–7",
        "\"His peace will guard your heart and mind.\"",
    ),
    "anxious": (
        "Peace is available to you right now.",
        "John 14:27",
        "\"My peace I give you. Do not let your heart be troubled.\"",
    ),
    "angry": (
        "Anger is worth hearing — but not obeying right now.",
        "Eph. 4:26",
        "\"In your anger do not sin.\"",
    ),
    "avoiding_something": (
        "One small step forward is enough.",
        "Prov. 3:5",
        "\"Trust in the Lord with all your heart.\"",
    ),
}

_DEFAULT_CONTENT = (
    "You reached out — that matters.",
    "Phil. 4:13",
    "\"I can do all things through Christ who strengthens me.\"",
)

CARD_WIDTH  = 264
CARD_HEIGHT = 128


class RecoveryNoteCard(QWidget):
    """Small floating note card shown beside the reason dialog.

    Emits ``dismissed(reason_id)`` when the × button is clicked so the
    caller can deselect the corresponding reason button.
    """

    dismissed = Signal(str)  # payload: reason_id

    def __init__(self, reason_id: str, label: str, parent=None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool,
        )
        self.reason_id = reason_id
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)

        encourage, ref, verse = REASON_CARD_CONTENT.get(reason_id, _DEFAULT_CONTENT)
        self._build_ui(label, encourage, ref, verse)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(
        self,
        label: str,
        encourage: str,
        ref: str,
        verse: str,
    ) -> None:
        self.setStyleSheet(
            f"QWidget {{"
            f"  background-color: {COLOR_SURFACE};"
            f"  border: 1px solid {COLOR_ACCENT};"
            f"  border-radius: 8px;"
            f"}}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(4)

        # ── Header row: reason label + close button ──────────────────
        header = QHBoxLayout()
        header.setSpacing(4)
        header.setContentsMargins(0, 0, 0, 0)

        lbl_reason = QLabel(label)
        lbl_reason.setStyleSheet(
            f"color: {COLOR_ACCENT_DARK}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_NORMAL}pt; font-weight: 700;"
            f"background: transparent; border: none;"
        )
        header.addWidget(lbl_reason)
        header.addStretch()

        close_btn = QPushButton("×")
        close_btn.setFixedSize(18, 18)
        close_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: transparent; border: none;"
            f"  color: {COLOR_TEXT_MUTED}; font-size: 14px; padding: 0;"
            f"}}"
            f"QPushButton:hover {{ color: {COLOR_TEXT}; }}"
        )
        close_btn.clicked.connect(lambda: self.dismissed.emit(self.reason_id))
        close_btn.clicked.connect(self.close)
        header.addWidget(close_btn)
        root.addLayout(header)

        # ── Encouragement text ────────────────────────────────────────
        lbl_enc = QLabel(encourage)
        lbl_enc.setWordWrap(True)
        lbl_enc.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_SMALL}pt; background: transparent; border: none;"
        )
        root.addWidget(lbl_enc)

        # ── Scripture reference + quote ───────────────────────────────
        lbl_verse = QLabel(f"<b>{ref}</b>&nbsp;&nbsp;<i>{verse}</i>")
        lbl_verse.setTextFormat(Qt.TextFormat.RichText)
        lbl_verse.setWordWrap(True)
        lbl_verse.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_SMALL}pt; background: transparent; border: none;"
        )
        root.addWidget(lbl_verse)

        root.addStretch()
