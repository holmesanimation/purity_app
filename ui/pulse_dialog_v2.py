"""Pulse Dialog v2 — a random prayer recipient plus the journal tabs.

Replaces the legacy sliders/health/notes ``PulseDialog`` (preserved as
``ui.pulse_dialog_v1``).  There are no required fields; pressing "Done"
always completes the pulse.
"""

from __future__ import annotations

import random
import traceback
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from services.fake_journal import FakeJournalService
from services.notes_setup import notes_writer as journal_notes_writer, prayer_notes_writer
from services.pulse_models import PendingPulse, PulseSliders
from styles.theme import COLOR_ACCENT, COLOR_BACKGROUND, COLOR_TEXT
from ui.left_dock_dashboard import _DashboardJournalPanel


class PulseDialogV2(QDialog):
    def __init__(
        self,
        *,
        pending: PendingPulse,
        submit_pulse: Callable[..., None],
        prayer_recipient_names: list[str] | None = None,
        bible_library=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._pending = pending
        self._submit_pulse_cb = submit_pulse
        self._completed = False

        self.setWindowTitle("Pulse")
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumSize(720, 720)

        recipient_name = random.choice(prayer_recipient_names) if prayer_recipient_names else None
        self._build_ui(recipient_name, bible_library)

    def reject(self) -> None:
        if self._completed:
            super().reject()

    def _build_ui(self, recipient_name: str | None, bible_library) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(14)

        name_lbl = QLabel(recipient_name or "Add prayer recipients via Tools \u2192 Prayer Tool")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet(
            f"font-size: 24px; font-weight: 800; color: {COLOR_ACCENT};"
        )
        root.addWidget(name_lbl)

        self._journal_panel = _DashboardJournalPanel(
            journal_service=FakeJournalService(),
            bible_library=bible_library,
            notes_writer=journal_notes_writer,
            prayer_recipient_name=recipient_name,
            prayer_notes_writer=prayer_notes_writer,
        )
        root.addWidget(self._journal_panel, stretch=1)

        done_row = QHBoxLayout()
        done_row.addStretch()
        done_btn = QPushButton("Done")
        done_btn.clicked.connect(self._on_done)
        done_row.addWidget(done_btn)
        root.addLayout(done_row)

        self.setStyleSheet(
            f"QDialog {{ background: {COLOR_BACKGROUND}; color: {COLOR_TEXT}; }}"
        )

    def _on_done(self) -> None:
        try:
            self._submit_pulse_cb(
                sliders=PulseSliders(),
                answers={},
                note_text="",
                reach_out_text="",
                reach_out_sent=False,
                evening_duration_choice=None,
            )
        except Exception as exc:
            traceback.print_exc()
            QMessageBox.critical(self, "Pulse Submit Failed", str(exc))
            return
        self._completed = True
        self.accept()
