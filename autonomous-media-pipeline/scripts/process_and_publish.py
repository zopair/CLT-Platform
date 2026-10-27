"""Download, process, and publish a short from a configured source channel."""
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
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
# Set SOURCE_CHANNELS to your own staging/raw channels. The fallback is Blender Studio.
DEFAULT_SOURCE_CHANNELS = ["https://www.youtube.com/@BlenderStudio"]
TEMP = Path(tempfile.mkdtemp(prefix="media-pipeline-"))
CACHE = TEMP / "cache"
CACHE.mkdir(parents=True, exist_ok=True)


def main():
    try:
        raw_sources = os.environ.get("SOURCE_CHANNELS", "").strip()
        urls = [x.strip() for x in raw_sources.splitlines() if x.strip()] if raw_sources else DEFAULT_SOURCE_CHANNELS
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

        download_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "outtmpl": str(TEMP / "source.%(ext)s"),
            "noplaylist": True, "quiet": True, "cachedir": str(CACHE),
        }
        with YoutubeDL(download_opts) as ydl:
            ydl.download([info["webpage_url"]])
        sources = [p for p in TEMP.glob("source*") if p.suffix.lower() == ".mp4" and p.is_file()]
        if not sources:
            raise RuntimeError("Download did not produce MP4.")

        output = TEMP / "processed.mp4"
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-y", "-i", str(sources[0]), "-t", "55",
             "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "28",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+faststart", str(output)],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("FFmpeg completed without a usable output file.")
        print(f"Processing succeeded: {output.name} ({output.stat().st_size} bytes)")

        token = os.environ.get("YOUTUBE_TOKEN_JSON", "").strip()
        if not token:
            print("YOUTUBE_TOKEN_JSON is not configured; skipping upload. Download and FFmpeg processing succeeded.")
            return

        creds = Credentials.from_authorized_user_info(json.loads(token), SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
            else:
                raise RuntimeError("YouTube OAuth token is invalid. Generate a fresh token with generate_token.py.")
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        title = (info.get("title") or "Animated short")[:100]
        author = info.get("uploader") or info.get("channel") or "Original creator"
        description = (
            f"Source: {info['webpage_url']}\nCreator: {author}\n"
            "Original source supplied by the configured source channel."
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
        response = None
        while response is None:
            _, response = req.next_chunk()
        print("Uploaded public video; ID:", response.get("id"))
    finally:
        shutil.rmtree(TEMP, ignore_errors=True)
        for p in ROOT.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".mp4", ".part", ".ytdl"}:
                try:
                    p.unlink()
                except OSError:
                    pass


if __name__ == "__main__":
    main()
