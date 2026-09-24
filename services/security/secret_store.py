"""Generic secret-storage abstraction.

Namespace + name identify a secret (e.g. namespace ``"purity_app.dropbox"``,
name ``"refresh_token"``). Values are always strings. Implementations must
never store secrets in plaintext, never log secret values, and never fall
back silently to an insecure store.
"""

from __future__ import annotations

from typing import Protocol


class SecretStore(Protocol):
    def set_secret(self, namespace: str, name: str, value: str) -> None: ...

    def get_secret(self, namespace: str, name: str) -> str | None: ...

    def delete_secret(self, namespace: str, name: str) -> None: ...
