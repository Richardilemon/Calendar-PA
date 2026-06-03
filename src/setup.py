import os
import base64
from pathlib import Path

def setup_google_credentials():
    """
    On Render, Google credentials are stored as base64 env vars.
    Decode them to files at startup.
    """
    credentials_b64 = os.getenv("GOOGLE_CREDENTIALS_B64")
    token_b64       = os.getenv("GOOGLE_TOKEN_B64")
    
    credentials_file = os.getenv("CREDENTIALS_FILE", "credentials.json")
    token_file       = os.getenv("TOKEN_FILE",       "token.json")

    if credentials_b64:
        Path(credentials_file).parent.mkdir(parents=True, exist_ok=True)
        Path(credentials_file).write_bytes(base64.b64decode(credentials_b64))

    if token_b64:
        Path(token_file).parent.mkdir(parents=True, exist_ok=True)
        Path(token_file).write_bytes(base64.b64decode(token_b64))

    # ensure data directory exists
    data_dir = Path(os.getenv("CONTEXT_FILE", "./data/session_context.json")).parent
    data_dir.mkdir(parents=True, exist_ok=True)