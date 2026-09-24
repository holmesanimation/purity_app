"""In-process single-flight lock preventing overlapping backup runs.

Non-blocking: callers must use ``try_acquire()`` and never wait on it.
Shared by manual (P2) and scheduled (P3) trigger paths within one process.
"""

from __future__ import annotations

import threading


class SingleFlightLock:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def try_acquire(self) -> bool:
        return self._lock.acquire(blocking=False)

    def release(self) -> None:
        self._lock.release()

    @property
    def locked(self) -> bool:
        return self._lock.locked()
