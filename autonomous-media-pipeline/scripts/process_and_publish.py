"""Download, process, and publish an authorized short to the configured YouTube channel."""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from yt_dlp import YoutubeDL

ROOT = Path(__file__).resolve().parents[1]
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
TARGET_HANDLE = os.environ.get("YOUTUBE_TARGET_HANDLE", "@Alyzopair").strip().lower()
TEMP = Path(tempfile.mkdtemp(prefix="media-pipeline-"))
CACHE = TEMP / "cache"
CACHE.mkdir(parents=True, exist_ok=True)


def main():
    try:
        print("[1/5] Discovering configured authorized source channels...")
        raw_sources = os.environ.get("SOURCE_CHANNELS", "").strip()
        urls = [x.strip() for x in raw_sources.splitlines() if x.strip()]
        if not urls:
            raise RuntimeError(
                "SOURCE_CHANNELS is required. Configure only channels/videos you own "
                "or are authorized to republish."
            )

        opts = {
            "quiet": True, "no_warnings": True, "noplaylist": False,
            "skip_download": True, "cachedir": str(CACHE),
        }
        info = None
        with YoutubeDL(opts) as ydl:
            for url in urls:
                candidate = ydl.extract_info(url, download=False)
                entries = [e for e in (candidate or {}).get("entries", []) if e]
                if entries:
                    entries.sort(key=lambda e: str(e.get("upload_date") or ""), reverse=True)
                    info = next((e for e in entries if e.get("webpage_url")), None)
                elif candidate and candidate.get("webpage_url"):
                    info = candidate
                if info:
                    break
        if not info or not info.get("webpage_url"):
            raise RuntimeError("No usable video found in SOURCE_CHANNELS. Check the configured source channels.")

        print(f"[1/5] Source selected: {info['webpage_url']}")
        print("[2/5] Downloading source...")
        download_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4", "outtmpl": str(TEMP / "source.%(ext)s"),
            "noplaylist": True, "quiet": True, "cachedir": str(CACHE),
        }
        with YoutubeDL(download_opts) as ydl:
            ydl.download([info["webpage_url"]])
        sources = [p for p in TEMP.glob("source*") if p.suffix.lower() == ".mp4" and p.is_file()]
        if not sources:
            raise RuntimeError("Download did not produce MP4.")

        print(f"[2/5] Download complete: {sources[0].name}")
        print("[3/5] Encoding vertical video with standard FFmpeg settings...")
        output = TEMP / "processed.mp4"
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-y", "-i", str(sources[0]), "-t", "55",
                "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "28",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", str(output),
            ],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("FFmpeg completed without a usable output file.")
        print(f"[3/5] Processing succeeded: {output.name} ({output.stat().st_size} bytes)")

        token = os.environ.get("YOUTUBE_TOKEN_JSON", "").strip()
        if not token:
            raise RuntimeError("YOUTUBE_TOKEN_JSON is not configured; refusing to report success without a real upload.")
        creds = Credentials.from_authorized_user_info(json.loads(token), SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
            else:
                raise RuntimeError("YouTube OAuth token is invalid or lacks a refresh token. Re-authorize the intended channel.")

        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        channel_response = yt.channels().list(part="id,snippet", mine=True).execute()
        channels = channel_response.get("items", [])
        if not channels:
            raise RuntimeError("OAuth credentials do not identify a YouTube channel.")

        def normalize_handle(value):
            return (value or "").strip().lower().rstrip("/").split("/")[-1].lstrip("@")

        expected = TARGET_HANDLE.lstrip("@")
        matched = [
            c for c in channels
            if normalize_handle(c.get("snippet", {}).get("customUrl")) == expected
        ]
        if not matched:
            found = ", ".join(
                c.get("snippet", {}).get("customUrl", c.get("snippet", {}).get("title", "unknown"))
                for c in channels
            )
            raise RuntimeError(
                f"Authenticated channel could not be verified as {TARGET_HANDLE}; "
                f"API returned: {found}. No upload performed."
            )
        channel_id = matched[0]["id"]
        print(f"[4/5] Authenticated target channel verified: {TARGET_HANDLE} ({channel_id})")

        title = (info.get("title") or "Animated short")[:100]
        author = info.get("uploader") or info.get("channel") or "Original creator"
        description = (
            f"{title}\n\nOriginal source: {info['webpage_url']}\nCreator: {author}\n"
            "Edited into a vertical short. Source attribution is provided for transparency."
        )
        body = {
            "snippet": {
                "title": title, "description": description, "categoryId": "1",
                "tags": ["Shorts", "Animation"],
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": True,
            },
        }
        req = yt.videos().insert(
            part="snippet,status", body=body,
            media_body=MediaFileUpload(str(output), mimetype="video/mp4", resumable=True),
        )
        print("[4/5] Uploading video publicly to verified YouTube channel...")
        response = None
        while response is None:
            _, response = req.next_chunk()
        video_id = response.get("id")
        if not video_id:
            raise RuntimeError("YouTube upload response did not contain a video ID.")
        verification = yt.videos().list(part="id,status,snippet", id=video_id).execute()
        items = verification.get("items", [])
        if not items or items[0].get("id") != video_id:
            raise RuntimeError(f"Upload returned video ID {video_id}, but follow-up verification could not find it.")
        item = items[0]
        privacy = item.get("status", {}).get("privacyStatus", "unknown")
        print(f"[4/5] Upload verified. Video ID: {video_id}; privacyStatus: {privacy}; channel: {channel_id}")
    finally:
        print("[5/5] Cleaning temporary downloads, encoded media, and cache...")
        shutil.rmtree(TEMP, ignore_errors=True)
        # Remove only known generated/cache paths; never delete arbitrary repository MP4 assets.
        shutil.rmtree(ROOT / ".cache", ignore_errors=True)
        shutil.rmtree(ROOT / "__pycache__", ignore_errors=True)
        print("[5/5] Cleanup finished.")


if __name__ == "__main__":
    main()
