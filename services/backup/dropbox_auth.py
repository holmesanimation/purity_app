"""Dropbox OAuth2 authorization (offline/refresh-token flow, no local redirect server).

Uses ``DropboxOAuth2FlowNoRedirect`` with PKCE (``use_pkce=True``): the user
opens an authorize URL in a browser, approves access, and pastes the
resulting auth code back into the app. This yields a long-lived refresh
token, which is the only credential persisted (via
``DropboxCredentialStore``); the auth code itself is single-use and never
stored. No app secret is required — PKCE-issued refresh tokens don't need
one, either for the initial exchange or for later refresh calls.
"""

from __future__ import annotations

from dataclasses import dataclass

from dropbox import DropboxOAuth2FlowNoRedirect

from .credentials import DropboxCredentialStore


@dataclass
class DropboxAuthResult:
    refresh_token: str
    account_id: str | None


class DropboxAuthFlow:
    """Wraps a single in-progress authorization attempt."""

    def __init__(self, app_key: str) -> None:
        self._flow = DropboxOAuth2FlowNoRedirect(
            app_key,
            token_access_type="offline",
            use_pkce=True,
        )

    def start(self) -> str:
        """Return the URL the user must open in a browser to approve access."""
        return self._flow.start()

    def finish(self, auth_code: str) -> DropboxAuthResult:
        """Exchange the pasted auth code for a refresh token."""
        result = self._flow.finish(auth_code.strip())
        return DropboxAuthResult(
            refresh_token=result.refresh_token,
            account_id=getattr(result, "account_id", None),
        )


def complete_authorization(
    app_key: str,
    auth_code: str,
    *,
    flow: DropboxAuthFlow | None = None,
    credential_store: DropboxCredentialStore | None = None,
) -> DropboxAuthResult:
    """Finish an auth flow and persist the resulting refresh token."""
    flow = flow or DropboxAuthFlow(app_key)
    result = flow.finish(auth_code)
    store = credential_store or DropboxCredentialStore()
    store.set_refresh_token(result.refresh_token)
    return result
