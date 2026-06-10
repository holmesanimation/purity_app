from __future__ import annotations

import os
import traceback
from dataclasses import dataclass
from datetime import datetime
from typing import Callable


@dataclass(slots=True)
class ActivitySnapshot:
    had_new_activity: bool
    last_activity_at: datetime | None


class UserActivityMonitor:
    def __init__(
        self,
        *,
        clock_fn: Callable[[], datetime],
        cursor_reader: Callable[[], tuple[int, int] | None] | None = None,
        input_tick_reader: Callable[[], int | None] | None = None,
    ) -> None:
        self._clock_fn = clock_fn
        self._cursor_reader = cursor_reader or _read_cursor_position
        self._input_tick_reader = input_tick_reader or _read_last_input_tick_ms
        self._last_cursor: tuple[int, int] | None = None
        self._last_input_tick: int | None = None
        self._last_activity_at: datetime | None = None

    def poll(self) -> ActivitySnapshot:
        now = self._clock_fn()
        cursor = self._cursor_reader()
        input_tick = self._input_tick_reader()

        had_new_activity = False
        if cursor is not None:
            if self._last_cursor is None:
                self._last_cursor = cursor
            elif cursor != self._last_cursor:
                self._last_cursor = cursor
                had_new_activity = True

        if input_tick is not None:
            if self._last_input_tick is None:
                self._last_input_tick = input_tick
            elif input_tick != self._last_input_tick:
                self._last_input_tick = input_tick
                had_new_activity = True

        if had_new_activity:
            self._last_activity_at = now

        return ActivitySnapshot(
            had_new_activity=had_new_activity,
            last_activity_at=self._last_activity_at,
        )


def _read_cursor_position() -> tuple[int, int] | None:
    if os.name != "nt":
        return None

    try:
        import ctypes

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        point = POINT()
        if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            return None
        return int(point.x), int(point.y)
    except Exception:
        traceback.print_exc()
        return None


def _read_last_input_tick_ms() -> int | None:
    if os.name != "nt":
        return None

    try:
        import ctypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        return int(info.dwTime)
    except Exception:
        traceback.print_exc()
        return None