# ── Purity Forest Theme ────────────────────────────────────────
# Drop this in styles/theme.py, or import it as styles/theme_forest.py.
#
# Notes:
# - Uses local PNG assets under assets/theme/forest.
# - Qt QSS supports background-image URLs. Paths are resolved relative to the
#   process working directory, so the helper below creates absolute paths.

from pathlib import Path

_THEME_ROOT = Path(__file__).resolve().parents[1]
ASSET_FOREST_MOUNTAIN_LIGHT = (_THEME_ROOT / "assets" / "theme" / "forest" / "forest_mountain_light.png").as_posix()
ASSET_FOREST_INTERVENTION_DARK = (_THEME_ROOT / "assets" / "theme" / "forest" / "forest_intervention_dark.png").as_posix()
ASSET_SAGE_LEAF_WATERMARK = (_THEME_ROOT / "assets" / "theme" / "forest" / "sage_leaf_watermark.png").as_posix()

# ── Color Palette: masculine, muted nature ─────────────────────
COLOR_BACKGROUND = "#F4F6F2"      # fog-white with a green undertone
COLOR_SURFACE    = "#E7ECE5"      # pale sage card surface
COLOR_SURFACE_2  = "#DCE4D8"      # moss-tinted hover / alternate surface
COLOR_SURFACE_3  = "#CED8C9"      # deeper selected surface

COLOR_TEXT       = "#27302B"      # forest charcoal
COLOR_TEXT_MUTED = "#667067"      # weathered sage gray

COLOR_ACCENT       = "#4F6B52"    # forest sage
COLOR_ACCENT_DARK  = "#33483A"    # pine green
COLOR_ACCENT_LIGHT = "#7F9A81"    # eucalyptus highlight

COLOR_SUCCESS    = "#557C5F"      # moss
COLOR_WARNING    = "#B0894F"      # brass / warm bark
COLOR_DANGER     = "#8B4A4A"      # muted brick
COLOR_BORDER     = "#C9D2C7"      # sage border

COLOR_OVERLAY_DARK = "rgba(15, 27, 22, 180)"
COLOR_OVERLAY_LIGHT = "rgba(244, 246, 242, 188)"

# ── Font Definitions ───────────────────────────────────────────
FONT_FAMILY      = "Segoe UI"
FONT_SIZE_SMALL  = 10
FONT_SIZE_NORMAL = 11
FONT_SIZE_MEDIUM = 13
FONT_SIZE_LARGE  = 16
FONT_SIZE_TITLE  = 22

# ── Global QSS Stylesheet ─────────────────────────────────────
GLOBAL_QSS = f"""
/* ── Application base ── */
QWidget {{
    background-color: {COLOR_BACKGROUND};
    color: {COLOR_TEXT};
    font-family: "{FONT_FAMILY}";
    font-size: {FONT_SIZE_NORMAL}pt;
}}

QMainWindow {{
    background-color: {COLOR_BACKGROUND};
    background-image: url("{ASSET_FOREST_MOUNTAIN_LIGHT}");
    background-position: bottom center;
    background-repeat: no-repeat;
}}

QWidget[class="windowBackground"] {{
    background-color: {COLOR_BACKGROUND};
    background-image: url("{ASSET_FOREST_MOUNTAIN_LIGHT}");
    background-position: bottom center;
    background-repeat: no-repeat;
}}

QWidget[class="transparent"],
QScrollArea[class="transparent"] {{
    background: transparent;
    background-color: transparent;
    background-image: none;
}}

/* Optional dynamic properties:
   widget.setProperty("class", "hero")
   widget.setProperty("class", "interventionHero")
   widget.setProperty("class", "leafPanel")
*/

/* ── Nature background panels ── */
QWidget[class="hero"] {{
    background-color: {COLOR_SURFACE};
    background-image: url("{ASSET_FOREST_MOUNTAIN_LIGHT}");
    background-position: center;
    background-repeat: no-repeat;
    border: 1px solid {COLOR_BORDER};
    border-radius: 12px;
}}

QWidget[class="interventionHero"] {{
    background-color: {COLOR_ACCENT_DARK};
    background-image: url("{ASSET_FOREST_INTERVENTION_DARK}");
    background-position: center;
    background-repeat: no-repeat;
    border-radius: 12px;
}}

QWidget[class="leafPanel"] {{
    background-color: {COLOR_SURFACE};
    background-image: url("{ASSET_SAGE_LEAF_WATERMARK}");
    background-position: bottom right;
    background-repeat: no-repeat;
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
}}

/* ── Cards / Frames ── */
QFrame[class="card"],
QWidget[class="card"] {{
    background-color: rgba(231, 236, 229, 228);
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
}}

QFrame[class="statCard"],
QWidget[class="statCard"] {{
    background-color: rgba(244, 246, 242, 218);
    border: 1px solid rgba(201, 210, 199, 190);
    border-radius: 10px;
}}

/* ── Menu bar ── */
QMenuBar {{
    background-color: {COLOR_SURFACE};
    border-bottom: 1px solid {COLOR_BORDER};
    color: {COLOR_TEXT};
}}
QMenuBar::item {{
    padding: 5px 10px;
    background: transparent;
}}
QMenuBar::item:selected {{
    background-color: {COLOR_SURFACE_2};
    border-radius: 5px;
}}
QMenu {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 22px;
    border-radius: 5px;
}}
QMenu::item:selected {{
    background-color: {COLOR_SURFACE_2};
}}

/* ── Buttons ── */
QPushButton {{
    background-color: {COLOR_ACCENT};
    color: #FFFFFF;
    border: none;
    border-radius: 7px;
    padding: 7px 16px;
    font-size: {FONT_SIZE_NORMAL}pt;
    font-weight: 650;
}}
QPushButton:hover {{
    background-color: {COLOR_ACCENT_LIGHT};
    color: {COLOR_TEXT};
}}
QPushButton:pressed {{
    background-color: {COLOR_ACCENT_DARK};
    color: #FFFFFF;
}}
QPushButton:disabled {{
    background-color: {COLOR_SURFACE_2};
    color: {COLOR_TEXT_MUTED};
}}

QPushButton[flat="true"],
QPushButton[class="secondary"] {{
    background-color: transparent;
    color: {COLOR_ACCENT_DARK};
    border: 1px solid {COLOR_ACCENT_LIGHT};
}}
QPushButton[flat="true"]:hover,
QPushButton[class="secondary"]:hover {{
    background-color: {COLOR_SURFACE_2};
}}

/* ── Tabs ── */
QTabWidget::pane {{
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    background-color: {COLOR_SURFACE};
}}
QTabBar::tab {{
    background-color: {COLOR_BACKGROUND};
    color: {COLOR_TEXT_MUTED};
    padding: 7px 18px;
    border: 1px solid {COLOR_BORDER};
    border-bottom: none;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
}}
QTabBar::tab:selected {{
    background-color: {COLOR_SURFACE};
    color: {COLOR_ACCENT_DARK};
    font-weight: 700;
}}
QTabBar::tab:hover {{
    background-color: {COLOR_SURFACE_2};
}}

/* ── Text inputs ── */
QTextEdit, QLineEdit, QPlainTextEdit {{
    background-color: rgba(244, 246, 242, 230);
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 5px 9px;
    color: {COLOR_TEXT};
    selection-background-color: {COLOR_ACCENT_LIGHT};
}}
QTextEdit:focus, QLineEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {COLOR_ACCENT};
    background-color: #FAFBF7;
}}

/* ── Labels ── */
QLabel {{
    background-color: transparent;
    color: {COLOR_TEXT};
}}

QLabel[class="title"] {{
    color: {COLOR_TEXT};
    font-size: {FONT_SIZE_TITLE}pt;
    font-weight: 800;
}}

QLabel[class="muted"] {{
    color: {COLOR_TEXT_MUTED};
}}

/* ── List widgets ── */
QListWidget {{
    background-color: {COLOR_BACKGROUND};
    border: 1px solid {COLOR_BORDER};
    border-radius: 7px;
    padding: 3px;
}}
QListWidget::item {{
    padding: 5px 9px;
    border-radius: 5px;
}}
QListWidget::item:hover {{
    background-color: {COLOR_SURFACE_2};
}}
QListWidget::item:selected {{
    background-color: {COLOR_SURFACE_3};
    color: {COLOR_TEXT};
}}

/* ── Tables ── */
QTableView, QTreeView {{
    background-color: {COLOR_BACKGROUND};
    alternate-background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    gridline-color: {COLOR_BORDER};
    selection-background-color: {COLOR_SURFACE_3};
    selection-color: {COLOR_TEXT};
}}
QHeaderView::section {{
    background-color: {COLOR_SURFACE};
    color: {COLOR_TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {COLOR_BORDER};
    padding: 6px 8px;
    font-weight: 700;
}}

/* ── Scroll areas ── */
QScrollArea {{
    border: none;
    background-color: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 9px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {COLOR_BORDER};
    border-radius: 4px;
    min-height: 22px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLOR_ACCENT_LIGHT};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* ── Group boxes ── */
QGroupBox {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 9px;
    margin-top: 9px;
    padding: 9px;
    font-weight: 700;
    color: {COLOR_TEXT_MUTED};
    font-size: {FONT_SIZE_SMALL}pt;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 7px;
}}

/* ── Checkboxes ── */
QCheckBox {{
    spacing: 7px;
    color: {COLOR_TEXT};
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    background-color: {COLOR_BACKGROUND};
}}
QCheckBox::indicator:hover {{
    border-color: {COLOR_ACCENT_LIGHT};
}}
QCheckBox::indicator:checked {{
    background-color: {COLOR_SUCCESS};
    border-color: {COLOR_SUCCESS};
}}

/* ── Progress bars ── */
QProgressBar {{
    background-color: {COLOR_SURFACE_2};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    text-align: center;
    color: {COLOR_TEXT};
}}
QProgressBar::chunk {{
    background-color: {COLOR_ACCENT};
    border-radius: 5px;
}}

/* ── Tooltips ── */
QToolTip {{
    background-color: {COLOR_ACCENT_DARK};
    color: #FFFFFF;
    border: 1px solid {COLOR_ACCENT_LIGHT};
    border-radius: 6px;
    padding: 6px;
}}
"""
