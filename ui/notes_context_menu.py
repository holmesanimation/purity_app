"""App-wide right-click context menu that exposes the notes system.

Install once on the QApplication instance:

    filter = NotesContextMenuFilter(app)
    app.installEventFilter(filter)

Any widget that receives a ContextMenu event will show a small menu with:
    • Add Note      → opens NoteDialog with useful app-level context
    • Browse Notes  → opens / raises NotesBrowserWindow
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QMenu, QWidget

from services.notes_setup import notes_writer, notes_repo
from ui.notes.note_dialog import NoteDialog
from ui.notes.notes_browser_window import NotesBrowserWindow


def _build_context(obj: QWidget) -> dict:
    """Return a context dict that describes *obj* in app terms, not Qt terms.

    * ``widget_class`` — Qt class name (e.g. ``"QPushButton"``)
    * ``widget_text``  — visible text on the widget, if any
    * ``owner_class``  — first ancestor whose class lives outside PySide6
    * ``owner_module`` — dotted module of that ancestor (helps locate the file)
    """
    widget_text = ""
    if hasattr(obj, "text") and callable(obj.text):
        try:
            widget_text = obj.text() or ""
        except Exception:
            pass

    owner_class = ""
    owner_module = ""
    parent = obj.parent()
    while parent is not None:
        mod = type(parent).__module__ or ""
        if not mod.startswith("PySide6"):
            owner_class = type(parent).__name__
            owner_module = mod
            break
        parent = parent.parent()

    return {
        "widget_class": type(obj).__name__,
        "widget_text": widget_text,
        "owner_class": owner_class,
        "owner_module": owner_module,
    }


class NotesContextMenuFilter(QObject):
    """Event filter installed on QApplication to intercept right-clicks app-wide."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._browser: NotesBrowserWindow | None = None

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ContextMenu and isinstance(obj, QWidget):
            menu = QMenu(obj)
            add_action = menu.addAction("📝  Add Note")
            browse_action = menu.addAction("📂  Browse Notes")

            chosen = menu.exec(event.globalPos())

            if chosen is add_action:
                dlg = NoteDialog(
                    writer=notes_writer,
                    owner="purity",
                    context=_build_context(obj),
                    parent=obj,
                )
                dlg.exec()

            elif chosen is browse_action:
                self._open_browser(obj)

            # Always consume — prevents the widget's own context menu from
            # also appearing (e.g. QTextEdit copy/paste strip).
            return True

        return False

    def open_browser(self, parent: QWidget | None = None) -> None:
        """Programmatically open / raise the browser window."""
        self._open_browser(parent)

    def _open_browser(self, parent: QWidget | None) -> None:
        if self._browser is None:
            self._browser = NotesBrowserWindow(repository=notes_repo, parent=None)
            self._browser.set_writer(notes_writer)
        self._browser.show()
        self._browser.raise_()
        self._browser.activateWindow()
        self._browser.refresh()


    def open_browser(self, parent: QWidget | None = None) -> None:
        """Programmatically open / raise the browser window."""
        self._open_browser(parent)

    def _open_browser(self, parent: QWidget | None) -> None:
        if self._browser is None:
            self._browser = NotesBrowserWindow(repository=notes_repo, parent=None)
            self._browser.set_writer(notes_writer)
        self._browser.show()
        self._browser.raise_()
        self._browser.activateWindow()
        self._browser.refresh()
