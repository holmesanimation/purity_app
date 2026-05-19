# ── Color Palette ──────────────────────────────────────────────
COLOR_BACKGROUND = "#FAF9F6"      # off-white page background
COLOR_SURFACE    = "#F5F0E8"      # warm beige card surface
COLOR_SURFACE_2  = "#EDE8DF"      # slightly deeper surface for hover/alt rows
COLOR_TEXT       = "#2D2926"      # charcoal primary text
COLOR_TEXT_MUTED = "#7A736B"      # muted secondary text
COLOR_ACCENT     = "#8B6F47"      # warm brown accent
COLOR_ACCENT_LIGHT = "#C4A882"    # lighter accent for borders/highlights
COLOR_SUCCESS    = "#4A7C59"      # muted green
COLOR_WARNING    = "#C47C2B"      # warm amber
COLOR_DANGER     = "#A83232"      # muted red
COLOR_BORDER     = "#DDD8CF"      # subtle border color

# ── Font Definitions ───────────────────────────────────────────
FONT_FAMILY      = "Segoe UI"
FONT_SIZE_SMALL  = 10
FONT_SIZE_NORMAL = 11
FONT_SIZE_MEDIUM = 13
FONT_SIZE_LARGE  = 16
FONT_SIZE_TITLE  = 20

# ── Global QSS Stylesheet ─────────────────────────────────────
GLOBAL_QSS = f"""
/* ── Application base ── */
QWidget {{
    background-color: {COLOR_BACKGROUND};
    color: {COLOR_TEXT};
    font-family: "{FONT_FAMILY}";
    font-size: {FONT_SIZE_NORMAL}pt;
}}

/* ── Cards / Frames ── */
QFrame[class="card"] {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
}}

/* ── Buttons ── */
QPushButton {{
    background-color: {COLOR_ACCENT};
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-size: {FONT_SIZE_NORMAL}pt;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {COLOR_ACCENT_LIGHT};
    color: {COLOR_TEXT};
}}
QPushButton:pressed {{
    background-color: {COLOR_SURFACE_2};
    color: {COLOR_TEXT};
}}
QPushButton[flat="true"] {{
    background-color: transparent;
    color: {COLOR_ACCENT};
    border: 1px solid {COLOR_ACCENT_LIGHT};
}}
QPushButton[flat="true"]:hover {{
    background-color: {COLOR_SURFACE_2};
}}

/* ── Tabs ── */
QTabWidget::pane {{
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    background-color: {COLOR_SURFACE};
}}
QTabBar::tab {{
    background-color: {COLOR_BACKGROUND};
    color: {COLOR_TEXT_MUTED};
    padding: 6px 16px;
    border: 1px solid {COLOR_BORDER};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-size: {FONT_SIZE_NORMAL}pt;
}}
QTabBar::tab:selected {{
    background-color: {COLOR_SURFACE};
    color: {COLOR_TEXT};
    font-weight: 600;
}}
QTabBar::tab:hover {{
    background-color: {COLOR_SURFACE_2};
}}

/* ── Text inputs ── */
QTextEdit, QLineEdit, QPlainTextEdit {{
    background-color: {COLOR_BACKGROUND};
    border: 1px solid {COLOR_BORDER};
    border-radius: 5px;
    padding: 4px 8px;
    color: {COLOR_TEXT};
    font-size: {FONT_SIZE_NORMAL}pt;
    selection-background-color: {COLOR_ACCENT_LIGHT};
}}
QTextEdit:focus, QLineEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {COLOR_ACCENT_LIGHT};
}}

/* ── Labels ── */
QLabel {{
    background-color: transparent;
    color: {COLOR_TEXT};
    font-size: {FONT_SIZE_NORMAL}pt;
}}

/* ── List widgets ── */
QListWidget {{
    background-color: {COLOR_BACKGROUND};
    border: 1px solid {COLOR_BORDER};
    border-radius: 5px;
    padding: 2px;
}}
QListWidget::item {{
    padding: 4px 8px;
    border-radius: 4px;
}}
QListWidget::item:selected {{
    background-color: {COLOR_SURFACE_2};
    color: {COLOR_TEXT};
}}

/* ── Scroll areas ── */
QScrollArea {{
    border: none;
    background-color: transparent;
}}
QScrollBar:vertical {{
    background: {COLOR_SURFACE};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {COLOR_BORDER};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* ── Group boxes ── */
QGroupBox {{
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    margin-top: 8px;
    padding: 8px;
    font-weight: 600;
    color: {COLOR_TEXT_MUTED};
    font-size: {FONT_SIZE_SMALL}pt;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
}}

/* ── Checkboxes ── */
QCheckBox {{
    spacing: 6px;
    font-size: {FONT_SIZE_NORMAL}pt;
    color: {COLOR_TEXT};
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {COLOR_BORDER};
    border-radius: 3px;
    background-color: {COLOR_BACKGROUND};
}}
QCheckBox::indicator:checked {{
    background-color: {COLOR_SUCCESS};
    border-color: {COLOR_SUCCESS};
}}
"""
