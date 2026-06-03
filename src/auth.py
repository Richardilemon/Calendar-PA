import os
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv
load_dotenv()

# Scopes define what access we're requesting
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
]

# Paths
BASE_DIR     = Path(__file__).parent.parent
CREDS_FILE = Path(os.getenv("CREDENTIALS_FILE", str(BASE_DIR / "credentials.json")))
TOKEN_FILE  = Path(os.getenv("TOKEN_FILE",       str(BASE_DIR / "token.json")))


def get_calendar_service():
    """
    Returns an authenticated Google Calendar service.
    Handles the full OAuth flow on first run, then uses
    the saved token on subsequent runs.
    """
    creds = None

    # load saved token if it exists
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    # if no valid credentials, run the OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # silently refresh expired token
            creds.refresh(Request())
        else:
            # first time — open browser for user to authorize
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=8080)

        # save token for next time
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)