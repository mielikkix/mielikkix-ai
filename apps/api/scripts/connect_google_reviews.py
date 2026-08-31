"""One-time local setup for Review & Reputation's Google Business Profile
integration (see apps/agents/review-reputation/CLAUDE.md) -- connects ONE
real Business Profile location for local dev/testing, by running Google's
own "installed app" OAuth flow: this opens your browser, you sign in and
approve access, then this script lists the Business Profile accounts and
locations that account can manage and asks you to pick one, then prints the
GOOGLE_REVIEWS_* values to paste into your .env. You only run this once (or
again if you want to connect a different location) -- the running app
itself never does this interactive flow, it only ever refreshes the token
this produces (see app/integrations/google_reviews_client.py).

Prerequisites (do these first, in order -- unlike Calendar API, Business
Profile access is NOT self-serve just by enabling an API in Cloud Console):

    1. Request Business Profile API access from Google:
       https://support.google.com/business/answer/l/api_default
       This is a manual approval Google grants per developer/project --
       there is no way around this step, and it can take some time.
    2. Once approved, in that same Google Cloud project: enable "My
       Business Business Information API" and "My Business Account
       Management API" (APIs & Services -> Library).
    3. Create credentials -> OAuth client ID -> Application type
       "Desktop app". Note the Client ID and Client Secret it gives you --
       this script asks for both below.
    4. Make sure the Google account you sign in with in step 5 below is
       actually a Manager/Owner on a VERIFIED Business Profile listing
       (business.google.com) -- an unverified listing won't show up as a
       location this script can connect.

Usage:
    cd apps/api
    python scripts/connect_google_reviews.py
"""

import sys
from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.integrations.google_reviews_client import REVIEWS_SCOPES  # noqa: E402

# Account Management API -- lists which Business Profile accounts (not
# locations yet) this signed-in user can manage. Separate REST API/host
# from the v4 reviews endpoints google_reviews_client.py itself calls.
_ACCOUNT_MANAGEMENT_BASE = "https://mybusinessaccountmanagement.googleapis.com/v1"
# Business Information API -- lists the locations within one account.
_BUSINESS_INFORMATION_BASE = "https://mybusinessbusinessinformation.googleapis.com/v1"


def _choose(items: list[dict], label_fn, prompt: str) -> dict:
    for i, item in enumerate(items, start=1):
        print(f"  {i}. {label_fn(item)}")
    while True:
        choice = input(prompt).strip()
        if choice.isdigit() and 1 <= int(choice) <= len(items):
            return items[int(choice) - 1]
        print(f"Enter a number between 1 and {len(items)}.")


def main() -> None:
    print("Paste the Client ID and Client Secret from your Google Cloud")
    print("OAuth client (Application type: Desktop app) below.\n")
    client_id = input("Client ID: ").strip()
    client_secret = input("Client Secret: ").strip()

    if not client_id or not client_secret:
        print("Both values are required -- see this script's docstring for how to get them.")
        sys.exit(1)

    # Same "installed" (not "web") flow as scripts/connect_google_calendar.py,
    # for the same reason -- see that script's own comment.
    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=REVIEWS_SCOPES,
    )

    print("\nOpening your browser to sign in and approve access...")
    credentials = flow.run_local_server(port=0)
    credentials.refresh(Request())
    headers = {"Authorization": f"Bearer {credentials.token}"}

    print("\nLooking up the Business Profile accounts this login can manage...")
    accounts_response = requests.get(f"{_ACCOUNT_MANAGEMENT_BASE}/accounts", headers=headers, timeout=15)
    accounts_response.raise_for_status()
    accounts = accounts_response.json().get("accounts", [])
    if not accounts:
        print(
            "No Business Profile accounts found for this login. Make sure you signed in with an "
            "account that's a Manager/Owner on a VERIFIED Business Profile listing, and that "
            "Google has approved your Business Profile API access request (see this script's "
            "docstring, prerequisite 1)."
        )
        sys.exit(1)

    account = _choose(accounts, lambda a: f"{a.get('accountName', '(unnamed)')} ({a['name']})", "\nAccount number: ")
    account_id = account["name"].split("/")[-1]

    print(f"\nLooking up locations under {account['name']}...")
    locations_response = requests.get(
        f"{_BUSINESS_INFORMATION_BASE}/{account['name']}/locations",
        headers=headers,
        params={"readMask": "title,name"},
        timeout=15,
    )
    locations_response.raise_for_status()
    locations = locations_response.json().get("locations", [])
    if not locations:
        print("No locations found under that account.")
        sys.exit(1)

    location = _choose(locations, lambda l: f"{l.get('title', '(untitled)')} ({l['name']})", "\nLocation number: ")
    location_id = location["name"].split("/")[-1]

    print("\nConnected. Add these to your .env:\n")
    print(f"GOOGLE_REVIEWS_CLIENT_ID={client_id}")
    print(f"GOOGLE_REVIEWS_CLIENT_SECRET={client_secret}")
    print(f"GOOGLE_REVIEWS_REFRESH_TOKEN={credentials.refresh_token}")
    print(f"GOOGLE_REVIEWS_ACCOUNT_ID={account_id}")
    print(f"GOOGLE_REVIEWS_LOCATION_ID={location_id}")


if __name__ == "__main__":
    main()
