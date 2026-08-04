from __future__ import annotations

import traceback
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services.pulse_models import PendingPulse, PulseKind, PulseSliders
from styles.theme import COLOR_ACCENT, COLOR_ACCENT_LIGHT, COLOR_BACKGROUND, COLOR_BORDER, COLOR_SURFACE, COLOR_TEXT

# (positive, neutral, negative) button ids → PulseSliders values
_STATE_BUTTON_VALUES = (3, 0, -3)

_STATE_ROWS = [
    ("Energized", "Tired"),
    ("Peacefilled", "Stressed"),
    ("Not Tempted", "Tempted"),
]
_STATE_EMOJIS = [
    ("\U0001f600", "#22c55e"),  # 😀 green
    ("\U0001f610", "#f97316"),  # 😐 orange
    ("\U0001f61e", "#ef4444"),  # 😞 red
]


def _state_btn_style(checked: bool, color: str) -> str:
    if checked:
        return (
            f"font-size: 22px; border-radius: 24px; "
            f"background: #22c55e40; border: 2px solid {color};"
        )
    return "font-size: 22px; border-radius: 24px; background: transparent; border: 2px solid transparent;"


class PulseDialog(QDialog):
    def __init__(
        self,
        *,
        pending: PendingPulse,
        submit_pulse: Callable[..., None],
        submit_note: Callable[[str], None],
        send_reach_out: Callable[[PulseSliders, str], None],
        verse_text: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._pending = pending
        self._submit_pulse_cb = submit_pulse
        self._submit_note_cb = submit_note
        self._send_reach_out_cb = send_reach_out
        self._verse_text = verse_text
        self._note_sent = False
        self._reach_out_sent = False
        self._completed = False
        self._state_groups: list[QButtonGroup] = []

        self.setWindowTitle(self._title_for_pending())
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumSize(720, 720)
        self._build_ui()
        self._refresh_submit_enabled()

    def reject(self) -> None:
        if self._completed:
            super().reject()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(14)

        title = QLabel(self._title_for_pending())
        title.setStyleSheet(
            f"font-size: 24px; font-weight: 800; color: {COLOR_ACCENT};"
        )
        root.addWidget(title)

        if self._verse_text:
            verse_label = QLabel(self._verse_text)
            verse_label.setWordWrap(True)
            verse_label.setStyleSheet(
                f"font-style: italic; color: {COLOR_TEXT}; padding: 12px; "
                f"border: 1px solid {COLOR_BORDER}; border-radius: 8px; background: {COLOR_SURFACE};"
            )
            root.addWidget(verse_label)

        subtitle = QLabel("Complete this pulse before returning to the app.")
        subtitle.setStyleSheet(f"color: {COLOR_TEXT};")
        root.addWidget(subtitle)

        root.addWidget(self._build_state_group())
        root.addWidget(self._build_health_group())
        root.addWidget(self._build_notes_group())

        self._submit_status = QLabel("")
        self._submit_status.setWordWrap(True)
        root.addWidget(self._submit_status)

        submit_row = QHBoxLayout()
        submit_row.addStretch()
        self._submit_btn = QPushButton("Submit Pulse")
        self._submit_btn.clicked.connect(self._on_submit_pulse)
        submit_row.addWidget(self._submit_btn)
        root.addLayout(submit_row)

        self.setStyleSheet(
            f"QDialog {{ background: {COLOR_BACKGROUND}; color: {COLOR_TEXT}; }}"
            f"QGroupBox {{ border: 1px solid {COLOR_BORDER}; border-radius: 10px; margin-top: 12px; background: {COLOR_SURFACE}; }}"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
            "QPlainTextEdit { border: 1px solid #6b7280; border-radius: 8px; padding: 8px; background: white; color: black; }"
            "QPushButton { padding: 8px 10px; }"
        )

    def _build_state_group(self) -> QGroupBox:
        group = QGroupBox("My State")
        layout = QGridLayout(group)
        layout.setVerticalSpacing(12)
        layout.setColumnStretch(0, 2)
        layout.setColumnStretch(4, 2)

        for row_idx, (positive, negative) in enumerate(_STATE_ROWS):
            pos_label = QLabel(positive)
            pos_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(pos_label, row_idx, 0)

            btn_group = QButtonGroup(group)
            btn_group.setExclusive(True)

            for btn_id, (emoji, color) in enumerate(_STATE_EMOJIS):
                btn = QPushButton(emoji)
                btn.setCheckable(True)
                btn.setFixedSize(48, 48)
                btn.setStyleSheet(_state_btn_style(False, color))
                btn.toggled.connect(
                    lambda checked, b=btn, c=color: b.setStyleSheet(_state_btn_style(checked, c))
                )
                btn.toggled.connect(self._on_state_changed)
                btn_group.addButton(btn, btn_id)
                layout.addWidget(btn, row_idx, btn_id + 1)

            self._state_groups.append(btn_group)

            neg_label = QLabel(negative)
            neg_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(neg_label, row_idx, 4)

        reach_out_btn = QPushButton("Reach Out to Group")
        reach_out_btn.setEnabled(False)
        reach_out_btn.clicked.connect(self._on_reach_out)
        layout.addWidget(reach_out_btn, len(_STATE_ROWS), 0, 1, 5)
        self._reach_out_btn = reach_out_btn

        return group

    def _build_health_group(self) -> QGroupBox:
        group = QGroupBox("Health")
        layout = QVBoxLayout(group)

        vitamins_row = QHBoxLayout()
        self._vitamins_btn = QPushButton("\U0001f48a I did not take my vitamins today")
        self._vitamins_btn.setCheckable(True)
        self._vitamins_btn.toggled.connect(
            lambda checked: self._vitamins_btn.setText(
                "\U0001f48a I took my vitamins today" if checked
                else "\U0001f48a I did not take my vitamins today"
            )
        )
        self._vitamins_btn.setStyleSheet(
            f"QPushButton {{ background-color: #98B39A; color: white; border: none; border-radius: 7px; }}"
            f"QPushButton:hover {{ background-color: {COLOR_ACCENT_LIGHT}; color: {COLOR_TEXT}; }}"
            f"QPushButton:checked {{ background-color: {COLOR_ACCENT}; color: white; border: none; }}"
            f"QPushButton:checked:hover {{ background-color: {COLOR_ACCENT}; color: white; border: none; }}"
        )
        vitamins_row.addWidget(self._vitamins_btn)
        vitamins_row.addStretch()
        layout.addLayout(vitamins_row)

        layout.addWidget(QLabel("What physical activity did you do today?"))
        self._physical_activity_edit = QPlainTextEdit()
        self._physical_activity_edit.setMinimumHeight(72)
        layout.addWidget(self._physical_activity_edit)

        return group

    def _build_notes_group(self) -> QGroupBox:
        group = QGroupBox("Notes")
        layout = QVBoxLayout(group)
        self._note_edit = QPlainTextEdit()
        self._note_edit.setPlaceholderText("Write a note to your journal...")
        self._note_edit.setMinimumHeight(90)
        layout.addWidget(self._note_edit)
        row = QHBoxLayout()
        self._note_btn = QPushButton("Submit Note")
        self._note_btn.clicked.connect(self._on_submit_note)
        row.addWidget(self._note_btn)
        row.addStretch()
        layout.addLayout(row)
        self._note_status = QLabel("")
        self._note_status.setWordWrap(True)
        layout.addWidget(self._note_status)
        return group

    def _title_for_pending(self) -> str:
        return {
            PulseKind.MANUAL: "Manual Pulse",
            PulseKind.MORNING: "Morning Pulse",
            PulseKind.AFTERNOON: "Afternoon Pulse",
            PulseKind.EVENING: "Evening Pulse",
        }[self._pending.pulse_kind]

    def _current_sliders(self) -> PulseSliders:
        def _val(group_idx: int) -> int:
            checked_id = self._state_groups[group_idx].checkedId()
            if 0 <= checked_id < len(_STATE_BUTTON_VALUES):
                return _STATE_BUTTON_VALUES[checked_id]
            return 0

        return PulseSliders(
            energy=_val(0),
            faith=_val(1),
            encouragement=0,
            temptation=_val(2),
        )

    def _on_state_changed(self) -> None:
        self._refresh_submit_enabled()
        self._refresh_reach_out_enabled()

    def _refresh_submit_enabled(self) -> None:
        all_selected = all(group.checkedId() != -1 for group in self._state_groups)
        self._submit_btn.setEnabled(all_selected)

    def _refresh_reach_out_enabled(self) -> None:
        any_negative = any(group.checkedId() == 2 for group in self._state_groups)
        self._reach_out_btn.setEnabled(any_negative)

    def _on_submit_note(self) -> None:
        text = self._note_edit.toPlainText().strip()
        if not text:
            self._note_status.setText("Enter a note before submitting it.")
            return
        self._submit_note_cb(text)
        self._note_sent = True
        self._note_status.setText("Note submitted.")

    def _on_reach_out(self) -> None:
        message, ok = QInputDialog.getMultiLineText(
            self,
            "Reach Out to Group",
            "Write a message to the group:",
        )
        if not ok or not message.strip():
            return
        self._send_reach_out_cb(self._current_sliders(), message.strip())
        self._reach_out_sent = True

    def _on_submit_pulse(self) -> None:
        try:
            self._submit_pulse_cb(
                sliders=self._current_sliders(),
                answers={
                    "took_vitamins": self._vitamins_btn.isChecked(),
                    "physical_activity": self._physical_activity_edit.toPlainText().strip(),
                },
                note_text=self._note_edit.toPlainText().strip(),
                reach_out_text="",
                reach_out_sent=self._reach_out_sent,
                evening_duration_choice=None,
            )
        except Exception as exc:
            traceback.print_exc()
            QMessageBox.critical(self, "Pulse Submit Failed", str(exc))
            return
        self._completed = True
        self.accept()