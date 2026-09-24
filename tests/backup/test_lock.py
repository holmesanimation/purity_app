from __future__ import annotations

from services.backup.lock import SingleFlightLock


def test_first_acquire_succeeds() -> None:
    lock = SingleFlightLock()
    assert lock.try_acquire() is True
    assert lock.locked is True


def test_second_acquire_fails_while_locked() -> None:
    lock = SingleFlightLock()
    assert lock.try_acquire() is True
    assert lock.try_acquire() is False


def test_release_allows_reacquire() -> None:
    lock = SingleFlightLock()
    lock.try_acquire()
    lock.release()
    assert lock.locked is False
    assert lock.try_acquire() is True
