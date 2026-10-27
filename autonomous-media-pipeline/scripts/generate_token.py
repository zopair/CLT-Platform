"""Generate a YouTube upload OAuth token JSON for GitHub Actions.

One-time setup:
1. Download an OAuth Client ID JSON from Google Cloud (Desktop app) and save as
   client_secret.json, or set YOUTUBE_CLIENT_SECRETS_JSON to its JSON contents.
2. Run: python generate_token.py
3. Copy the printed JSON into the GitHub Actions secret YOUTUBE_TOKEN_JSON.
"""
import json
import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main():
    raw = os.environ.get("YOUTUBE_CLIENT_SECRETS_JSON", "").strip()
    if raw:
        client_config = json.loads(raw)
    else:
        path = Path("client_secret.json")
        if not path.is_file():
            raise SystemExit(
                "Missing OAuth client JSON. Save it as client_secret.json "
                "or set YOUTUBE_CLIENT_SECRETS_JSON."
            )
        client_config = json.loads(path.read_text(encoding="utf-8"))

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    credentials = flow.run_local_server(port=0, prompt="consent", authorization_prompt_message="Open this URL to authorize: {url}")
    print("\nCopy the following JSON into GitHub Secret YOUTUBE_TOKEN_JSON:\n")
    print(credentials.to_json())


if __name__ == "__main__":
    main()
