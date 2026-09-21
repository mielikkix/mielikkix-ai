"""Shared token-refresh helper for the two Stage 12 providers
(analytics_provider.py, search_console_provider.py) -- both read from the
same SeoGoogleConnection row (one Google account, one OAuth client, two
read-only reporting scopes granted together, see app/api/google_oauth.py),
so refreshing an access token from the stored refresh token is identical
work for both. Not shared with google_calendar_client.py's own
_build_credentials: that one is scoped to CalendarConnection/
CALENDAR_SCOPES, a different connection row entirely, and duplicating one
small function is cheaper than a shared abstraction two genuinely
different OAuth connections would have to bend around.

Talks to Google's token endpoint directly via `requests` (not
googleapiclient's default httplib2 transport) for the same reason
google_calendar_client.py already does -- see that module's own docstring
on the confirmed-live httplib2/IPv6 issue on this dev machine.
"""
import requests
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


class GoogleTokenRefreshError(Exception):
    """Raised when a stored refresh token can no longer mint an access
    token -- expired, revoked, or the OAuth client's own credentials
    changed. Callers treat this exactly like "not connected" (return None/
    empty, never fabricate a number) rather than raising further, since a
    stale connection isn't a code bug."""


def get_access_token(client_id: str, client_secret: str, refresh_token: str, scopes: list[str]) -> str:
    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes,
    )
    try:
        credentials.refresh(Request())
    except google_auth_exceptions.GoogleAuthError as exc:
        raise GoogleTokenRefreshError(f"Google token refresh failed: {exc}") from exc
    return credentials.token


REQUEST_TIMEOUT_SECONDS = 15
