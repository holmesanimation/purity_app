"""Secure storage for Dropbox credentials via a Windows DPAPI-backed secret store.

Only the refresh token is a secret here — retrieved through
``WindowsDpapiSecretStore`` (current-user DPAPI encryption). Never write it
to settings.yaml, QSettings, backup state JSON, logs, audit records, the
local backup tree, or Dropbox itself.

The Dropbox app secret is no longer needed or stored: authorization uses a
PKCE-capable ``DropboxOAuth2FlowNoRedirect`` flow (see ``dropbox_auth.py``),
and refreshing a PKCE-issued refresh token does not require a client secret.

Non-secret Dropbox configuration (enabled flag, app key, remote folder,
auth-invalid flag) belongs in ``settings_schemas.py`` instead.
"""

from __future__ import annotations

from services.security.secret_store import SecretStore
from services.security.windows_dpapi_store import WindowsDpapiSecretStore

_NAMESPACE = "purity_app.dropbox"
_NAME_REFRESH_TOKEN = "refresh_token"


class DropboxCredentialStore:
    """Thin, mockable abstraction over a ``SecretStore`` for Dropbox secrets."""

    def __init__(self, *, store: SecretStore | None = None, namespace: str = _NAMESPACE) -> None:
        self._store = store or WindowsDpapiSecretStore()
        self._namespace = namespace

    def get_refresh_token(self) -> str | None:
        return self._store.get_secret(self._namespace, _NAME_REFRESH_TOKEN)

    def set_refresh_token(self, value: str) -> None:
        self._store.set_secret(self._namespace, _NAME_REFRESH_TOKEN, value)

    def clear_refresh_token(self) -> None:
        self._store.delete_secret(self._namespace, _NAME_REFRESH_TOKEN)

    def clear_all(self) -> None:
        self.clear_refresh_token()
