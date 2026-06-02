# Re-export the Purity Forest theme as the active theme.
# All consumers use `from styles.theme import ...` - this file is the single switch point.
from ui.themes.purity_forest_theme.styles.theme_forest import *  # noqa: F401, F403
