"""One-time local setup for Booking Assistant's Phase 1 (see
apps/agents/booking-assistant/CLAUDE.md) -- connects ONE real Google
Calendar for local dev/testing, by running Google's own "installed app"
OAuth flow: this opens your browser, you sign in and approve access, and
this script prints the three GOOGLE_CALENDAR_* values to paste into your
.env. You only run this once (or again if you want to connect a different
test calendar) -- the running app itself never does this interactive flow,
it only ever refreshes the token this produces (see
app/integrations/google_calendar_client.py).

Prerequisite (Phase 0, do this first in Google Cloud Console):
    1. Create a Google Cloud project (or use an existing one).
    2. Enable the "Google Calendar API" for it (APIs & Services -> Library).
    3. Create credentials -> OAuth client ID -> Application type
       "Desktop app". Note the Client ID and Client Secret it gives you --
       this script asks for both below.
    (Phase 5's real per-tenant dashboard flow will need a SEPARATE "Web
    application" Client ID later -- see this agent's CLAUDE.md. This
    Desktop app one is for local dev/testing only.)

Usage:
    cd apps/api
    python scripts/connect_google_calendar.py
"""

import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.integrations.google_calendar_client import CALENDAR_SCOPE  # noqa: E402


def main() -> None:
    print("Paste the Client ID and Client Secret from your Google Cloud")
    print("OAuth client (Application type: Desktop app) below.\n")
    client_id = input("Client ID: ").strip()
    client_secret = input("Client Secret: ").strip()

    if not client_id or not client_secret:
        print("Both values are required -- see this script's docstring for how to get them.")
        sys.exit(1)

    # from_client_config, not from_client_secrets_file: this app has no
    # reason to keep a separate client_secret.json file on disk just for a
    # script you run once -- the two values above are all that file would
    # ever contain anyway. "installed" (not "web") tells google-auth-oauthlib
    # this is the installed-app flow, matching the "Desktop app" client type
    # created in Google Cloud Console.
    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=[CALENDAR_SCOPE],
    )

    print("\nOpening your browser to sign in and approve access...")
    # port=0: let the OS pick a free local port for the temporary redirect
    # listener this spins up -- you don't need to configure a redirect URI
    # for a Desktop app client, unlike the Phase 5 Web application one.
    credentials = flow.run_local_server(port=0)

    print("\nConnected. Add these to your .env:\n")
    print(f"GOOGLE_CALENDAR_CLIENT_ID={client_id}")
    print(f"GOOGLE_CALENDAR_CLIENT_SECRET={client_secret}")
    print(f"GOOGLE_CALENDAR_REFRESH_TOKEN={credentials.refresh_token}")
    print("GOOGLE_CALENDAR_ID=primary")


if __name__ == "__main__":
    main()
