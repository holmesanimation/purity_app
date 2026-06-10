from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from services.pulse_models import PendingPulse, PulseKind, PulseSliders
from services.pulse_notifications import REACH_OUT_TITLE, REACH_OUT_VERSE
from styles.theme import COLOR_ACCENT, COLOR_BACKGROUND, COLOR_BORDER, COLOR_SURFACE, COLOR_TEXT


class PulseDialog(QDialog):
    def __init__(
        self,
        *,
        pending: PendingPulse,
        submit_pulse: Callable[..., None],
        submit_note: Callable[[str], None],
        send_reach_out: Callable[[PulseSliders, str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._pending = pending
        self._submit_pulse_cb = submit_pulse
        self._submit_note_cb = submit_note
        self._send_reach_out_cb = send_reach_out
        self._note_sent = False
        self._reach_out_sent = False
        self._completed = False
        self._slider_widgets: dict[str, QSlider] = {}
        self._slider_value_labels: dict[str, QLabel] = {}

        self.setWindowTitle(self._title_for_pending())
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumSize(720, 760)
        self._build_ui()
        self._refresh_reach_out_visibility()

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

        subtitle = QLabel("Complete this pulse before returning to the app.")
        subtitle.setStyleSheet(f"color: {COLOR_TEXT};")
        root.addWidget(subtitle)

        root.addWidget(self._build_sliders_group())
        root.addWidget(self._build_questions_group())
        root.addWidget(self._build_notes_group())
        root.addWidget(self._build_reach_out_group())

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
            "QComboBox, QPushButton { padding: 8px 10px; }"
        )

    def _build_sliders_group(self) -> QGroupBox:
        group = QGroupBox("Sliders")
        layout = QGridLayout(group)
        layout.setVerticalSpacing(12)
        slider_rows = [
            ("energy", "Tired", "Energized"),
            ("faith", "Anxious", "Faith Filled"),
            ("encouragement", "Discouraged", "Encouraged"),
            ("temptation", "Tempted", "Not Tempted"),
        ]
        for row, (key, left_label, right_label) in enumerate(slider_rows):
            label = QLabel(f"{left_label} <- -> {right_label}")
            layout.addWidget(label, row, 0)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(-5, 5)
            slider.setTickInterval(1)
            slider.setTickPosition(QSlider.TickPosition.TicksBelow)
            slider.setValue(0)
            slider.valueChanged.connect(self._refresh_slider_labels)
            slider.valueChanged.connect(self._refresh_reach_out_visibility)
            layout.addWidget(slider, row, 1)
            value_label = QLabel("0")
            value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(value_label, row, 2)
            self._slider_widgets[key] = slider
            self._slider_value_labels[key] = value_label
        return group

    def _build_questions_group(self) -> QGroupBox:
        group = QGroupBox("Questions")
        layout = QVBoxLayout(group)

        if self._pending.pulse_kind in (PulseKind.MORNING, PulseKind.MANUAL):
            layout.addWidget(QLabel("What did you learn from Scripture today about God?"))
            self._scripture_edit = QPlainTextEdit()
            self._scripture_edit.setMinimumHeight(90)
            layout.addWidget(self._scripture_edit)
            self._vitamins_check = QCheckBox("Did you take your vitamins?")
            layout.addWidget(self._vitamins_check)

        if self._pending.pulse_kind in (PulseKind.AFTERNOON, PulseKind.MANUAL):
            layout.addWidget(QLabel("What physical activity did you do today?"))
            self._physical_activity_edit = QPlainTextEdit()
            self._physical_activity_edit.setMinimumHeight(90)
            layout.addWidget(self._physical_activity_edit)

        if self._pending.pulse_kind in (PulseKind.EVENING, PulseKind.MANUAL):
            layout.addWidget(QLabel("What are you doing right now?"))
            self._evening_activity_edit = QPlainTextEdit()
            self._evening_activity_edit.setMinimumHeight(90)
            layout.addWidget(self._evening_activity_edit)
            layout.addWidget(QLabel("How long do you plan to keep doing it?"))
            self._duration_combo = QComboBox()
            self._duration_combo.addItems(["5m", "10m", "30m", "1h", "2h"])
            layout.addWidget(self._duration_combo)
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

    def _build_reach_out_group(self) -> QGroupBox:
        group = QGroupBox(REACH_OUT_TITLE)
        self._reach_out_group = group
        layout = QVBoxLayout(group)
        verse = QLabel(REACH_OUT_VERSE)
        verse.setWordWrap(True)
        layout.addWidget(verse)
        self._reach_out_edit = QPlainTextEdit()
        self._reach_out_edit.setPlaceholderText("Write a short message to the group...")
        self._reach_out_edit.setMinimumHeight(90)
        layout.addWidget(self._reach_out_edit)
        row = QHBoxLayout()
        self._reach_out_btn = QPushButton("Reach Out")
        self._reach_out_btn.clicked.connect(self._on_reach_out)
        row.addWidget(self._reach_out_btn)
        row.addStretch()
        layout.addLayout(row)
        self._reach_out_status = QLabel("")
        self._reach_out_status.setWordWrap(True)
        layout.addWidget(self._reach_out_status)
        return group

    def _title_for_pending(self) -> str:
        return {
            PulseKind.MANUAL: "Manual Pulse",
            PulseKind.MORNING: "Morning Pulse",
            PulseKind.AFTERNOON: "Afternoon Pulse",
            PulseKind.EVENING: "Evening Pulse",
        }[self._pending.pulse_kind]

    def _current_sliders(self) -> PulseSliders:
        return PulseSliders(
            energy=self._slider_widgets["energy"].value(),
            faith=self._slider_widgets["faith"].value(),
            encouragement=self._slider_widgets["encouragement"].value(),
            temptation=self._slider_widgets["temptation"].value(),
        )

    def _refresh_slider_labels(self) -> None:
        for key, label in self._slider_value_labels.items():
            label.setText(str(self._slider_widgets[key].value()))

    def _refresh_reach_out_visibility(self) -> None:
        self._reach_out_group.setVisible(self._current_sliders().any_negative())

    def _validate_answers(self) -> tuple[dict[str, object] | None, str | None]:
        if self._pending.pulse_kind is PulseKind.MANUAL:
            return {
                "scripture_learning": self._scripture_edit.toPlainText().strip(),
                "took_vitamins": self._vitamins_check.isChecked(),
                "physical_activity": self._physical_activity_edit.toPlainText().strip(),
                "what_are_you_doing_right_now": self._evening_activity_edit.toPlainText().strip(),
                "how_long_do_you_plan_to_keep_doing_it": self._duration_combo.currentText(),
            }, None

        if self._pending.pulse_kind is PulseKind.MORNING:
            scripture = self._scripture_edit.toPlainText().strip()
            if not scripture:
                return None, "Morning Pulse requires a Scripture reflection."
            return {
                "scripture_learning": scripture,
                "took_vitamins": self._vitamins_check.isChecked(),
            }, None

        if self._pending.pulse_kind is PulseKind.AFTERNOON:
            activity = self._physical_activity_edit.toPlainText().strip()
            if not activity:
                return None, "Afternoon Pulse requires a physical activity answer."
            return {"physical_activity": activity}, None

        current_activity = self._evening_activity_edit.toPlainText().strip()
        if not current_activity:
            return None, "Evening Pulse requires your current activity."
        return {
            "what_are_you_doing_right_now": current_activity,
            "how_long_do_you_plan_to_keep_doing_it": self._duration_combo.currentText(),
        }, None

    def _on_submit_note(self) -> None:
        text = self._note_edit.toPlainText().strip()
        if not text:
            self._note_status.setText("Enter a note before submitting it.")
            return
        self._submit_note_cb(text)
        self._note_sent = True
        self._note_status.setText("Note submitted.")

    def _on_reach_out(self) -> None:
        message = self._reach_out_edit.toPlainText().strip()
        if not message:
            self._reach_out_status.setText("Write a message before sending Reach Out.")
            return
        self._send_reach_out_cb(self._current_sliders(), message)
        self._reach_out_sent = True
        self._reach_out_btn.setEnabled(False)
        self._reach_out_status.setText("Reach Out sent.")

    def _on_submit_pulse(self) -> None:
        answers, error = self._validate_answers()
        if error is not None:
            self._submit_status.setText(error)
            return
        try:
            self._submit_pulse_cb(
                sliders=self._current_sliders(),
                answers=answers or {},
                note_text=self._note_edit.toPlainText().strip(),
                reach_out_text=self._reach_out_edit.toPlainText().strip(),
                reach_out_sent=self._reach_out_sent,
                evening_duration_choice=(
                    self._duration_combo.currentText()
                    if self._pending.pulse_kind in (PulseKind.EVENING, PulseKind.MANUAL)
                    else None
                ),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Pulse Submit Failed", str(exc))
            return
        self._completed = True
        self.accept()