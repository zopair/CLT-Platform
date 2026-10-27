# Autonomous Media Pipeline

GitHub Actions workflow for processing and uploading media you own or are explicitly licensed to republish.

## Required repository secrets
- `SOURCE_CHANNELS`: newline-separated authorized video/channel URLs.
- `YOUTUBE_TOKEN_JSON`: authorized YouTube OAuth token JSON with upload scope.
- `YOUTUBE_CLIENT_SECRETS_JSON`: OAuth client JSON for reference/setup.

The workflow uploads videos as **private** for review. Confirm license and attribution requirements. No browser cookies or OAuth bypasses are used.