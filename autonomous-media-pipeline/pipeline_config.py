"""Pure configuration policy for safe YouTube publishing."""

from __future__ import annotations

from collections.abc import Mapping

ALLOWED_PRIVACY_STATUSES = frozenset({"private", "unlisted", "public"})


def has_youtube_credentials(environ: Mapping[str, str]) -> bool:
    """Return whether a complete supported OAuth credential set is present."""
    if environ.get("YOUTUBE_TOKEN_JSON", "").strip():
        return True
    return all(
        environ.get(key, "").strip()
        for key in ("YOUTUBE_REFRESH_TOKEN", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET")
    )


def resolve_privacy_status(environ: Mapping[str, str]) -> str:
    """Default uploads to private; public visibility must be explicitly configured."""
    status = environ.get("YOUTUBE_PRIVACY_STATUS", "private").strip().lower() or "private"
    if status not in ALLOWED_PRIVACY_STATUSES:
        allowed = ", ".join(sorted(ALLOWED_PRIVACY_STATUSES))
        raise ValueError(f"YOUTUBE_PRIVACY_STATUS must be one of: {allowed}")
    return status
