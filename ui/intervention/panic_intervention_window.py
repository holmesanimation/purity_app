"""Panic intervention workspace window.

A top-level QMainWindow that guides the user through:
  1. Acknowledging each selected reason (with optional reflection text and
     a "Praise Jesus!" confirmation per topic).
  2. A countdown period with calm recovery prompts.
  3. A "Close Session" button that records a RECOVERED outcome.

Usage::

    window = PanicInterventionWindow(
        session=panic_session,
        runtime=runtime,   # may be None
        stats=panic_stats, # may be None
        parent=None,
    )
    window.show()
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)

from services.panic_session import PanicSession, PanicSessionOutcome, PanicSessionState
from styles.theme import (
    COLOR_ACCENT,
    COLOR_ACCENT_DARK,
    COLOR_ACCENT_LIGHT,
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_SURFACE,
    COLOR_SURFACE_2,
    COLOR_SURFACE_3,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    FONT_FAMILY,
    FONT_SIZE_LARGE,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_NORMAL,
    FONT_SIZE_SMALL,
    FONT_SIZE_TITLE,
)

if TYPE_CHECKING:
    from services.runtime import PurityRuntime

# ---------------------------------------------------------------------------
# Per-reason encouragement copy
# ---------------------------------------------------------------------------

_REASON_ENCOURAGEMENT: dict[str, tuple[str, str]] = {
    "home_alone": (
        "You are never truly alone.",
        "\"The Lord your God goes with you; He will never leave you nor forsake you.\" — Deuteronomy 31:6",
    ),
    "triggering_content": (
        "You can turn away. That choice is strength.",
        "\"Flee from youthful passions and pursue righteousness, faith, love, and peace.\" — 2 Timothy 2:22",
    ),
    "tired": (
        "Rest is a gift, not a weakness.",
        "\"Come to me, all who labor and are heavy laden, and I will give you rest.\" — Matthew 11:28",
    ),
    "hungry": (
        "Take care of your body — it is a gift.",
        "\"Man shall not live by bread alone, but by every word that comes from the mouth of God.\" — Matthew 4:4",
    ),
    "biological_urge": (
        "The urge is not a command. You have more power than it.",
        "\"God is faithful; He will not let you be tempted beyond what you can bear.\" — 1 Corinthians 10:13",
    ),
    "lonely": (
        "Loneliness is real — and God sees it.",
        "\"The Lord is near to the brokenhearted and saves the crushed in spirit.\" — Psalm 34:18",
    ),
    "discouraged": (
        "Discouragement is not the final word.",
        "\"Do not be anxious about anything, but in every situation, by prayer, present your requests to God.\" — Philippians 4:6",
    ),
    "anxious": (
        "Peace is available to you right now.",
        "\"Peace I leave with you; my peace I give you. Do not let your hearts be troubled.\" — John 14:27",
    ),
    "angry": (
        "Anger is worth listening to — but not obeying right now.",
        "\"In your anger do not sin. Do not let the sun go down while you are still angry.\" — Ephesians 4:26",
    ),
    "avoiding_something": (
        "Avoidance keeps the weight on. One small step forward is enough.",
        "\"Trust in the Lord with all your heart and lean not on your own understanding.\" — Proverbs 3:5",
    ),
}

_DEFAULT_ENCOURAGEMENT = (
    "You reached out — that matters.",
    "\"I can do all things through Christ who strengthens me.\" — Philippians 4:13",
)

_RECOVERY_PROMPTS: list[str] = [
    "Take a slow breath — in for four, out for six.",
    "Stand up, stretch, and drink a glass of water.",
    "Step outside or walk to another room.",
    "Say a short prayer — even a single honest sentence.",
    "Text or call someone you trust.",
    "Look out a window for thirty seconds.",
]

_COUNTDOWN_SECONDS = 5 * 60  # 5-minute default recovery window

# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------

_CARD_STYLE = (
    f"QFrame {{"
    f"  background-color: {COLOR_SURFACE_2};"
    f"  border: 1px solid {COLOR_BORDER};"
    f"  border-radius: 10px;"
    f"  padding: 6px;"
    f"}}"
)

_TOPIC_LABEL_STYLE = (
    f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
    f"font-size: {FONT_SIZE_MEDIUM}pt; font-weight: 700; background: transparent;"
)

_ENCOURAGE_STYLE = (
    f"color: {COLOR_ACCENT_DARK}; font-family: '{FONT_FAMILY}';"
    f"font-size: {FONT_SIZE_NORMAL}pt; font-style: italic; background: transparent;"
)

_SCRIPTURE_STYLE = (
    f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
    f"font-size: {FONT_SIZE_SMALL}pt; font-style: italic; background: transparent;"
)

_BTN_PRAISE_ENABLED = (
    f"QPushButton {{"
    f"  background-color: {COLOR_ACCENT};"
    f"  color: #ffffff;"
    f"  border: none;"
    f"  border-radius: 8px;"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {FONT_SIZE_NORMAL}pt;"
    f"  font-weight: 700;"
    f"  padding: 7px 18px;"
    f"}}"
    f"QPushButton:hover {{"
    f"  background-color: {COLOR_ACCENT_DARK};"
    f"}}"
)

_BTN_PRAISE_DONE = (
    f"QPushButton {{"
    f"  background-color: {COLOR_SURFACE_3};"
    f"  color: {COLOR_TEXT_MUTED};"
    f"  border: 1px solid {COLOR_BORDER};"
    f"  border-radius: 8px;"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {FONT_SIZE_NORMAL}pt;"
    f"  padding: 7px 18px;"
    f"}}"
)

_BTN_CLOSE_STYLE = (
    f"QPushButton {{"
    f"  background-color: {COLOR_ACCENT};"
    f"  color: #ffffff;"
    f"  border: none;"
    f"  border-radius: 10px;"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {FONT_SIZE_MEDIUM}pt;"
    f"  font-weight: 700;"
    f"  padding: 10px 32px;"
    f"}}"
    f"QPushButton:hover {{"
    f"  background-color: {COLOR_ACCENT_DARK};"
    f"}}"
)

_BTN_NOTIFY_STYLE = (
    f"QPushButton {{"
    f"  background-color: transparent;"
    f"  color: {COLOR_TEXT_MUTED};"
    f"  border: 1px solid {COLOR_BORDER};"
    f"  border-radius: 8px;"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {FONT_SIZE_SMALL}pt;"
    f"  padding: 6px 14px;"
    f"}}"
    f"QPushButton:hover {{"
    f"  background-color: {COLOR_SURFACE_2};"
    f"  color: {COLOR_TEXT};"
    f"}}"
)


class PanicInterventionWindow(QMainWindow):
    """Help workspace: reason panels → countdown → close session."""

    def __init__(
        self,
        *,
        session: PanicSession,
        runtime: Optional["PurityRuntime"] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.WindowStaysOnTopHint,
        )
        self._session = session
        self._runtime = runtime
        self._total_topics = len(session.selected_reason_ids)
        self._reoriented_count = 0
        self._countdown_seconds_remaining = _COUNTDOWN_SECONDS
        self._countdown_timer: Optional[QTimer] = None

        self.setWindowTitle("Recovery — You Are Not Alone")
        self.setMinimumSize(560, 480)
        self.resize(600, 640)

        central = QWidget()
        self.setCentralWidget(central)
        self._root_layout = QVBoxLayout(central)
        self._root_layout.setContentsMargins(24, 20, 24, 20)
        self._root_layout.setSpacing(14)

        self._build_header()
        self._build_reorientation_view()
        self._build_countdown_view()

        # Show reorientation view initially; countdown view hidden
        self._countdown_container.hide()

        self._center_on_screen()

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_header(self) -> None:
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        title = QLabel("Let's walk through this together.")
        title.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_MEDIUM}pt; font-weight: 700; background: transparent;"
        )
        header_row.addWidget(title, stretch=1)

        self._progress_label = QLabel(self._progress_text())
        self._progress_label.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_SMALL}pt; background: transparent;"
        )
        self._progress_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(self._progress_label)

        self._root_layout.addLayout(header_row)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"color: {COLOR_BORDER};")
        self._root_layout.addWidget(divider)

    def _progress_text(self) -> str:
        return f"{self._reoriented_count} / {self._total_topics} topics"

    # ------------------------------------------------------------------
    # Reorientation view
    # ------------------------------------------------------------------

    def _build_reorientation_view(self) -> None:
        self._reorientation_container = QWidget()
        reorientation_layout = QVBoxLayout(self._reorientation_container)
        reorientation_layout.setContentsMargins(0, 0, 0, 0)
        reorientation_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")

        cards_widget = QWidget()
        cards_widget.setStyleSheet("background: transparent;")
        self._cards_layout = QVBoxLayout(cards_widget)
        self._cards_layout.setContentsMargins(0, 0, 4, 0)
        self._cards_layout.setSpacing(12)

        self._praise_buttons: dict[str, QPushButton] = {}
        self._reflection_fields: dict[str, QTextEdit] = {}

        from ui.intervention.panic_reason_dialog import REASON_LABELS, _REASON_ID_TO_LABEL

        reason_label_map = dict(REASON_LABELS)

        for reason_id in self._session.selected_reason_ids:
            self._build_topic_card(reason_id, reason_label_map.get(reason_id, reason_id))

        self._cards_layout.addStretch()
        scroll.setWidget(cards_widget)
        reorientation_layout.addWidget(scroll)

        self._root_layout.addWidget(self._reorientation_container)

    def _build_topic_card(self, reason_id: str, label: str) -> None:
        encourage_text, scripture_text = _REASON_ENCOURAGEMENT.get(
            reason_id, _DEFAULT_ENCOURAGEMENT
        )

        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setStyleSheet(_CARD_STYLE)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(8)

        topic_lbl = QLabel(label)
        topic_lbl.setStyleSheet(_TOPIC_LABEL_STYLE)
        card_layout.addWidget(topic_lbl)

        encourage_lbl = QLabel(encourage_text)
        encourage_lbl.setWordWrap(True)
        encourage_lbl.setStyleSheet(_ENCOURAGE_STYLE)
        card_layout.addWidget(encourage_lbl)

        scripture_lbl = QLabel(scripture_text)
        scripture_lbl.setWordWrap(True)
        scripture_lbl.setStyleSheet(_SCRIPTURE_STYLE)
        card_layout.addWidget(scripture_lbl)

        reflection = QTextEdit()
        reflection.setPlaceholderText(
            "Reflect here, or simply press Praise Jesus to continue…"
        )
        reflection.setFixedHeight(80)
        reflection.setStyleSheet(
            f"QTextEdit {{"
            f"  background-color: {COLOR_SURFACE};"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  border-radius: 6px;"
            f"  color: {COLOR_TEXT};"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_NORMAL}pt;"
            f"  padding: 6px;"
            f"}}"
        )
        card_layout.addWidget(reflection)
        self._reflection_fields[reason_id] = reflection

        praise_btn = QPushButton("Praise Jesus!")
        praise_btn.setStyleSheet(_BTN_PRAISE_ENABLED)
        praise_btn.clicked.connect(lambda _checked=False, rid=reason_id: self._on_praise(rid))
        card_layout.addWidget(praise_btn, alignment=Qt.AlignmentFlag.AlignRight)
        self._praise_buttons[reason_id] = praise_btn

        self._cards_layout.addWidget(card)

    # ------------------------------------------------------------------
    # Countdown view
    # ------------------------------------------------------------------

    def _build_countdown_view(self) -> None:
        self._countdown_container = QWidget()
        countdown_layout = QVBoxLayout(self._countdown_container)
        countdown_layout.setContentsMargins(0, 0, 0, 0)
        countdown_layout.setSpacing(16)

        # Large timer display
        self._timer_label = QLabel(self._format_countdown())
        self._timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._timer_label.setStyleSheet(
            f"color: {COLOR_ACCENT_DARK}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_TITLE}pt; font-weight: 700; background: transparent;"
        )
        countdown_layout.addWidget(self._timer_label)

        recovery_title = QLabel("Take a moment:")
        recovery_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        recovery_title.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_SMALL}pt; font-weight: 600; background: transparent;"
        )
        countdown_layout.addWidget(recovery_title)

        for prompt in _RECOVERY_PROMPTS:
            prompt_lbl = QLabel(f"• {prompt}")
            prompt_lbl.setWordWrap(True)
            prompt_lbl.setStyleSheet(
                f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
                f"font-size: {FONT_SIZE_NORMAL}pt; background: transparent;"
            )
            countdown_layout.addWidget(prompt_lbl)

        countdown_layout.addStretch()

        # Notify group button (GUI-only stub)
        self._notify_btn = QPushButton("Notify Group For Prayer")
        self._notify_btn.setStyleSheet(_BTN_NOTIFY_STYLE)
        self._notify_btn.clicked.connect(self._on_notify_group)
        countdown_layout.addWidget(self._notify_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self._notify_confirm_label = QLabel("")
        self._notify_confirm_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._notify_confirm_label.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_SMALL}pt; font-style: italic; background: transparent;"
        )
        self._notify_confirm_label.hide()
        countdown_layout.addWidget(self._notify_confirm_label)

        # Close Session button (hidden until countdown complete)
        self._close_session_btn = QPushButton("Close Session")
        self._close_session_btn.setStyleSheet(_BTN_CLOSE_STYLE)
        self._close_session_btn.clicked.connect(self._on_close_session)
        self._close_session_btn.hide()
        countdown_layout.addWidget(self._close_session_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self._root_layout.addWidget(self._countdown_container)

    # ------------------------------------------------------------------
    # Slot handlers
    # ------------------------------------------------------------------

    def _on_praise(self, reason_id: str) -> None:
        """Acknowledge a topic — save optional reflection, lock the card."""
        from services.journal_events import (
            emit_panic_reflection_saved,
            emit_panic_topic_acknowledged,
        )

        reflection_field = self._reflection_fields[reason_id]
        reflection_text = reflection_field.toPlainText().strip()

        # Advance session state on first acknowledgement
        if self._session.state == PanicSessionState.SELECTING_REASONS:
            self._session.start_reflection()
            self._session.start_reorientation()
        elif self._session.state == PanicSessionState.REFLECTION:
            self._session.start_reorientation()

        self._session.reorient_topic(reason_id, reflection_text)

        # Emit journal events
        if self._runtime is not None:
            j = self._runtime.journal
            if reflection_text:
                emit_panic_reflection_saved(
                    j,
                    panic_session_id=self._session.panic_session_id,
                    reason_id=reason_id,
                )
            emit_panic_topic_acknowledged(
                j,
                panic_session_id=self._session.panic_session_id,
                reason_id=reason_id,
            )

        # Lock the card
        reflection_field.setReadOnly(True)
        btn = self._praise_buttons[reason_id]
        btn.setText("✓ Done")
        btn.setEnabled(False)
        btn.setStyleSheet(_BTN_PRAISE_DONE)

        # Update progress
        self._reoriented_count += 1
        self._progress_label.setText(self._progress_text())

        # When all topics acknowledged → start countdown
        if self._reoriented_count >= self._total_topics:
            self._start_countdown()

    def _start_countdown(self) -> None:
        """Transition to COUNTDOWN phase; swap to countdown view."""
        from services.journal_events import emit_panic_countdown_started

        self._session.start_countdown()

        if self._runtime is not None:
            emit_panic_countdown_started(
                self._runtime.journal,
                panic_session_id=self._session.panic_session_id,
                countdown_seconds=_COUNTDOWN_SECONDS,
            )

        self._reorientation_container.hide()
        self._countdown_container.show()

        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._tick_countdown)
        self._countdown_timer.start()

    def _tick_countdown(self) -> None:
        self._countdown_seconds_remaining -= 1
        self._timer_label.setText(self._format_countdown())

        if self._countdown_seconds_remaining <= 0:
            self._finish_countdown()

    def _finish_countdown(self) -> None:
        from services.journal_events import emit_panic_countdown_completed

        if self._countdown_timer is not None:
            self._countdown_timer.stop()
            self._countdown_timer = None

        self._session.complete_countdown()

        if self._runtime is not None:
            emit_panic_countdown_completed(
                self._runtime.journal,
                panic_session_id=self._session.panic_session_id,
            )

        self._timer_label.hide()
        self._close_session_btn.show()

    def _on_notify_group(self) -> None:
        """GUI-only stub — emits the journal event and shows a confirmation."""
        from services.journal_events import emit_panic_notify_group_clicked

        self._session.notify_stub_clicked = True

        if self._runtime is not None:
            emit_panic_notify_group_clicked(
                self._runtime.journal,
                panic_session_id=self._session.panic_session_id,
            )

        self._notify_btn.setEnabled(False)
        self._notify_confirm_label.setText("Your group will be notified.")
        self._notify_confirm_label.show()

    def _on_close_session(self) -> None:
        from services.journal_events import emit_panic_closed

        if self._session.state != PanicSessionState.CLOSED:
            self._session.close(PanicSessionOutcome.RECOVERED)
            if self._runtime is not None:
                emit_panic_closed(
                    self._runtime.journal,
                    panic_session_id=self._session.panic_session_id,
                    outcome=PanicSessionOutcome.RECOVERED.value,
                )

        self.close()

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Best-effort close — record ABANDONED if session not yet closed."""
        from services.journal_events import emit_panic_closed

        if self._session.state != PanicSessionState.CLOSED:
            try:
                self._session.close(PanicSessionOutcome.ABANDONED)
            except Exception:
                pass
            if self._runtime is not None:
                try:
                    emit_panic_closed(
                        self._runtime.journal,
                        panic_session_id=self._session.panic_session_id,
                        outcome=PanicSessionOutcome.ABANDONED.value,
                    )
                except Exception:
                    pass

        if self._countdown_timer is not None:
            self._countdown_timer.stop()

        event.accept()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_countdown(self) -> str:
        remaining = max(0, self._countdown_seconds_remaining)
        minutes, seconds = divmod(remaining, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def _center_on_screen(self) -> None:
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width()  - self.width())  // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        self.move(x, y)
