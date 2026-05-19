# purity_app/gui/log_viewer_window.py
"""PurityLogViewerWindow — standalone log viewer for purity_app."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableView, QTextEdit, QHeaderView, QLabel, QComboBox,
)

from shane_common.ui.log_viewer.log_table_model import (
    LogTableModel, LogFilterProxyModel,
    COL_TIMESTAMP, COL_MESSAGE, LOG_ROW_ROLE,
)
from shane_common.ui.log_viewer.base_normalizer_sink import BaseLogNormalizerSink
from shane_common.ui.log_viewer.log_row import LogRow
from shane_common.ui.log_viewer.log_row_emitter import CallbackLogRowEmitter

try:
    from purity_app.gui.log_normalizer_sink import PurityLogNormalizerSink
    from purity_app.services.log_kind_map import PURITY_TYPE_OPTIONS, spec_for_purity_kind
except ModuleNotFoundError:
    from gui.log_normalizer_sink import PurityLogNormalizerSink  # type: ignore[no-redef]
    from services.log_kind_map import (  # type: ignore[no-redef]
        PURITY_TYPE_OPTIONS,
        spec_for_purity_kind,
    )


def _row_key(row: LogRow) -> tuple:
    details = json.dumps(row.details, sort_keys=True, default=str, ensure_ascii=False)
    return (row.ts, row.kind, row.message, details)


def _load_disk_rows(data_root: Path) -> list[LogRow]:
    journals_root = Path(data_root) / "_system" / "purity" / "journals"
    if not journals_root.is_dir():
        return []

    captured: list[LogRow] = []

    class _ReplaySink(BaseLogNormalizerSink):
        pass

    sink = _ReplaySink(
        kind_spec_fn=spec_for_purity_kind,
        emitter=CallbackLogRowEmitter(on_row=lambda row: captured.append(row)),
    )

    for path in sorted(journals_root.glob("*/*.jsonl")):
        if path.name.startswith("run_tail."):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                envelope = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(envelope, dict):
                envelope.setdefault("_source_file", str(path))
                sink.emit(envelope)

    return sorted(captured, key=lambda row: row.ts)


class PurityLogViewerWindow(QMainWindow):
    """Log viewer window for purity_app.

    Connect sink to this window in ``app.py``::

        self._log_sink.emitter.log_row_appended.connect(
            self._log_viewer.append_row
        )
    """

    _SEVERITY_BUTTONS = ("DEBUG", "INFO", "WARN", "ERROR")

    def __init__(
        self,
        sink: PurityLogNormalizerSink,
        data_root: Path | str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Purity — Journal Viewer")
        self.resize(1100, 600)

        self._model = LogTableModel(
            type_classifier=sink.type_classifier,
            type_labels=sink.type_labels,
        )
        self._proxy = LogFilterProxyModel(type_classifier=sink.type_classifier)
        self._proxy.setSourceModel(self._model)

        self._build_ui()

        # Seed from disk first, then from buffered live rows emitted before this window opened.
        initial_rows: list[LogRow] = []
        if data_root is not None:
            initial_rows.extend(_load_disk_rows(Path(data_root)))
        initial_rows.extend(sink.emitter.drain_buffer())

        seen: set[tuple] = set()
        for row in sorted(initial_rows, key=lambda item: item.ts):
            key = _row_key(row)
            if key in seen:
                continue
            seen.add(key)
            self._model.append_row(row)

        self._restore_geometry()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def append_row(self, row) -> None:
        """Slot: called when sink emits a new LogRow."""
        self._model.append_row(row)
        # Auto-scroll to bottom.
        last = self._proxy.rowCount() - 1
        if last >= 0:
            self._table.scrollTo(self._proxy.index(last, 0))

    # ------------------------------------------------------------------ #
    # Internal build
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        root = QWidget()
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(4)

        vbox.addLayout(self._build_filter_bar())

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setVisible(False)
        hdr = self._table.horizontalHeader()
        hdr.setStretchLastSection(True)
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        # Fixed column widths.
        self._table.setColumnWidth(COL_TIMESTAMP, 90)
        self._table.setColumnWidth(1, 52)   # Level
        self._table.setColumnWidth(2, 52)   # Type
        self._table.setColumnWidth(3, 90)   # Instrument
        self._table.setColumnWidth(4, 140)  # Kind

        self._table.selectionModel().currentRowChanged.connect(self._on_row_changed)
        vbox.addWidget(self._table, stretch=3)

        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setMaximumHeight(140)
        self._detail.setPlaceholderText("Select a row to see details.")
        vbox.addWidget(self._detail, stretch=0)

        self.setCentralWidget(root)

    def _build_filter_bar(self) -> QHBoxLayout:
        hbox = QHBoxLayout()
        hbox.setSpacing(6)

        lbl = QLabel("Level:")
        hbox.addWidget(lbl)

        self._sev_buttons: dict[str, QPushButton] = {}
        for level in self._SEVERITY_BUTTONS:
            btn = QPushButton(level)
            btn.setCheckable(True)
            btn.setChecked(level in ("INFO", "WARN", "ERROR"))
            btn.setFixedWidth(58)
            btn.toggled.connect(lambda checked, lv=level: self._proxy.set_severity_enabled(lv, checked))
            hbox.addWidget(btn)
            self._sev_buttons[level] = btn

        type_lbl = QLabel("Type:")
        hbox.addWidget(type_lbl)

        self._type_combo = QComboBox()
        self._type_combo.setMinimumWidth(130)
        for label, mask in PURITY_TYPE_OPTIONS:
            self._type_combo.addItem(label, mask)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        hbox.addWidget(self._type_combo)

        hbox.addStretch()
        return hbox

    # ------------------------------------------------------------------ #
    # Slots
    # ------------------------------------------------------------------ #

    def _on_row_changed(self, current, _previous) -> None:
        src_idx = self._proxy.mapToSource(current)
        row = self._model.data(src_idx, LOG_ROW_ROLE)
        if row is None:
            self._detail.clear()
            return
        parts = [f"Kind:    {row.kind}", f"Message: {row.message}"]
        if row.details:
            try:
                details_str = json.dumps(row.details, indent=2, default=str, ensure_ascii=False)
            except Exception:
                details_str = str(row.details)
            parts.append(f"Details:\n{details_str}")
        self._detail.setPlainText("\n".join(parts))

    def _on_type_changed(self, _index: int) -> None:
        self._proxy.set_type_mask(int(self._type_combo.currentData()))

    # ------------------------------------------------------------------ #
    # Geometry persistence
    # ------------------------------------------------------------------ #

    def _restore_geometry(self) -> None:
        s = QSettings("purity", "PurityLogViewer")
        geom = s.value("geometry")
        state = s.value("windowState")
        if geom is not None:
            self.restoreGeometry(geom)
        if state is not None:
            self.restoreState(state)

    def closeEvent(self, event) -> None:
        s = QSettings("purity", "PurityLogViewer")
        s.setValue("geometry", self.saveGeometry())
        s.setValue("windowState", self.saveState())
        super().closeEvent(event)
