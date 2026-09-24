"""Purity-local secret storage (DPAPI-backed), replacing keyring/Credential Manager.

Structured as a generic ``SecretStore`` abstraction so it can be promoted to
``shane_common`` later without changing callers, if a second consumer (e.g.
the Trading App) needs the same mechanism.
"""
