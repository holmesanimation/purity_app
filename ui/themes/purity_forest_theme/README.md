# Purity Forest Theme

This package contains:

- `styles/theme_forest.py`
- `assets/theme/forest/forest_mountain_light.png`
- `assets/theme/forest/forest_intervention_dark.png`
- `assets/theme/forest/sage_leaf_watermark.png`

## Usage

Copy the `styles` and `assets` folders into your `purity_app` project root.

Then either:

```python
from styles.theme_forest import GLOBAL_QSS
```

or replace your existing `styles/theme.py` with `styles/theme_forest.py`.

Your app already imports `GLOBAL_QSS` from `styles.theme`, so the simplest path is:

1. Back up your current `styles/theme.py`
2. Rename `theme_forest.py` to `theme.py`
3. Keep the `assets/theme/forest` folder in the project root

## Optional widget background usage

To apply the mountain background to a dashboard hero widget:

```python
hero = QWidget()
hero.setProperty("class", "hero")
```

For a dark intervention popup panel:

```python
panel = QWidget()
panel.setProperty("class", "interventionHero")
```

For a note/journal panel with a subtle leaf watermark:

```python
panel = QWidget()
panel.setProperty("class", "leafPanel")
```

## Design intent

Muted forest/sage tones, soft fog backgrounds, pine-green accents, and restrained nature imagery. Masculine, calm, and devotional without becoming overpowering.
