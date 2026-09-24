from __future__ import annotations

from services.backup.credentials import DropboxCredentialStore


class _FakeSecretStore:
    """In-memory stand-in for a real ``SecretStore`` backend."""

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def set_secret(self, namespace: str, name: str, value: str) -> None:
        self._data[(namespace, name)] = value

    def get_secret(self, namespace: str, name: str) -> str | None:
        return self._data.get((namespace, name))

    def delete_secret(self, namespace: str, name: str) -> None:
        self._data.pop((namespace, name), None)


def test_refresh_token_round_trip() -> None:
    store = DropboxCredentialStore(store=_FakeSecretStore(), namespace="test.purity_app.dropbox")
    assert store.get_refresh_token() is None
    store.set_refresh_token("refresh-abc")
    assert store.get_refresh_token() == "refresh-abc"


def test_clear_all_removes_refresh_token_and_is_idempotent() -> None:
    store = DropboxCredentialStore(store=_FakeSecretStore(), namespace="test.purity_app.dropbox")
    store.set_refresh_token("refresh-abc")
    store.clear_all()
    assert store.get_refresh_token() is None
    # Clearing again must not raise even though nothing is stored.
    store.clear_all()


def test_different_namespaces_do_not_collide() -> None:
    backend = _FakeSecretStore()
    store_a = DropboxCredentialStore(store=backend, namespace="test.purity_app.dropbox.a")
    store_b = DropboxCredentialStore(store=backend, namespace="test.purity_app.dropbox.b")
    store_a.set_refresh_token("refresh-a")
    assert store_b.get_refresh_token() is None
