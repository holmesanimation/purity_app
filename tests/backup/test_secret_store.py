from __future__ import annotations

import sys

import pytest

if sys.platform != "win32":
    pytest.skip("Windows DPAPI secret store requires Windows.", allow_module_level=True)

from services.security.windows_dpapi_store import (
    SecretStoreError,
    WindowsDpapiSecretStore,
)


def test_set_and_get_round_trip(tmp_path) -> None:
    store = WindowsDpapiSecretStore(path=tmp_path / "secrets.dat")
    assert store.get_secret("ns", "name") is None
    store.set_secret("ns", "name", "s3cret-value")
    assert store.get_secret("ns", "name") == "s3cret-value"


def test_overwrite_replaces_value(tmp_path) -> None:
    store = WindowsDpapiSecretStore(path=tmp_path / "secrets.dat")
    store.set_secret("ns", "name", "first")
    store.set_secret("ns", "name", "second")
    assert store.get_secret("ns", "name") == "second"


def test_delete_removes_secret_and_is_idempotent(tmp_path) -> None:
    store = WindowsDpapiSecretStore(path=tmp_path / "secrets.dat")
    store.set_secret("ns", "name", "value")
    store.delete_secret("ns", "name")
    assert store.get_secret("ns", "name") is None
    store.delete_secret("ns", "name")  # must not raise


def test_missing_secret_returns_none(tmp_path) -> None:
    store = WindowsDpapiSecretStore(path=tmp_path / "secrets.dat")
    store.set_secret("ns", "other", "value")
    assert store.get_secret("ns", "name") is None


def test_namespace_isolation(tmp_path) -> None:
    store = WindowsDpapiSecretStore(path=tmp_path / "secrets.dat")
    store.set_secret("ns_a", "name", "value-a")
    assert store.get_secret("ns_b", "name") is None


def test_persisted_file_does_not_contain_plaintext_secret(tmp_path) -> None:
    path = tmp_path / "secrets.dat"
    store = WindowsDpapiSecretStore(path=path)
    secret_value = "super-secret-plaintext-marker-12345"
    store.set_secret("ns", "name", secret_value)

    raw_bytes = path.read_bytes()
    assert secret_value.encode("utf-8") not in raw_bytes


def test_corrupt_file_raises_explicit_error(tmp_path) -> None:
    path = tmp_path / "secrets.dat"
    path.write_text("{ not valid json", encoding="utf-8")
    store = WindowsDpapiSecretStore(path=path)
    with pytest.raises(SecretStoreError):
        store.get_secret("ns", "name")


def test_atomic_persistence_no_tmp_file_left_behind(tmp_path) -> None:
    path = tmp_path / "secrets.dat"
    store = WindowsDpapiSecretStore(path=path)
    store.set_secret("ns", "name", "value")
    assert path.exists()
    assert not path.with_suffix(".tmp").exists()
