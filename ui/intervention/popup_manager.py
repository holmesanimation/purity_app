from __future__ import annotations
from typing import Type
from ui.intervention.base_popup import BasePopup
from ui.intervention.web_popup import WebPopup
from ui.intervention.prayer_popup import PrayerPopup
from ui.intervention.risk_popup import RiskPopup
from ui.intervention.hourly_popup import HourlyPopup
from ui.intervention.evening_popup import EveningPopup

POPUP_TYPES = {
    "web":     WebPopup,
    "prayer":  PrayerPopup,
    "risk":    RiskPopup,
    "hourly":  HourlyPopup,
    "evening": EveningPopup,
}


class PopupManager:
    """Manages intervention popup instances; prevents duplicate open instances."""

    def __init__(self):
        self._instances: dict[str, BasePopup] = {}

    def trigger(self, popup_type: str) -> BasePopup | None:
        """Instantiate and show the requested popup type.

        If an instance is already visible, bring it to front instead of opening a second.
        """
        popup_class: Type[BasePopup] | None = POPUP_TYPES.get(popup_type)
        if popup_class is None:
            return None

        existing = self._instances.get(popup_type)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return existing

        popup = popup_class()
        self._instances[popup_type] = popup
        popup.show_centered()
        return popup
