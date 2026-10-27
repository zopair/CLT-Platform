"""Process only explicitly licensed Creative Commons videos before public upload."""
import json, os, shutil, subprocess, tempfile
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from yt_dlp import YoutubeDL

ROOT = Path(__file__).resolve().parents[1]
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
# Fallback discovery source only; each selected video must still declare a CC license.
DEFAULT_SOURCE_CHANNELS = ["https://www.youtube.com/@NASA"]
TEMP = Path(tempfile.mkdtemp(prefix="licensed-media-"))
CACHE = TEMP / "cache"
CACHE.mkdir(parents=True, exist_ok=True)

def has_reusable_cc_license(info):
    license_name = str(info.get("license") or "").strip().lower()
    return license_name in {"creativecommon", "creative commons attribution", "creative commons"}
    
def main():
    try:
        raw_sources = os.environ.get("SOURCE_CHANNELS", "").strip()
        urls = [x.strip() for x in raw_sources.splitlines() if x.strip()] if raw_sources else DEFAULT_SOURCE_CHANNELS
        opts = {"quiet": True, "no_warnings": True, "noplaylist": False, "skip_download": True, "cachedir": str(CACHE)}
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(urls[0], download=False)
        if info and info.get("entries"):
            entries = [e for e in info["entries"] if e]
            entries.sort(key=lambda e: str(e.get("upload_date") or ""), reverse=True)
            info = next((e for e in entries if has_reusable_cc_license(e)), None)
        if not info or not info.get("webpage_url"):
            raise RuntimeError("No video with a verifiable Creative Commons license found. Set SOURCE_CHANNELS to a source with CC-licensed videos.")
        if not has_reusable_cc_license(info):
            raise RuntimeError("Refusing to publish: source metadata does not identify a Creative Commons license.")
        download_opts = {"format":"bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best","merge_output_format":"mp4","outtmpl":str(TEMP/"source.%(ext)s"),"noplaylist":True,"quiet":True,"cachedir":str(CACHE)}
        with YoutubeDL(download_opts) as ydl:
            ydl.download([info["webpage_url"]])
        sources = [p for p in TEMP.glob("source*") if p.suffix.lower()==".mp4" and p.is_file()]
        if not sources:
            raise RuntimeError("Download did not produce MP4.")
        output = TEMP/"processed.mp4"
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
        subprocess.run(["ffmpeg","-hide_banner","-y","-i",str(sources[0]),"-t","55","-vf",vf,"-c:v","libx264","-preset","medium","-crf","28","-pix_fmt","yuv420p","-c:a","aac","-b:a","128k","-movflags","+faststart",str(output)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        token = os.environ.get("YOUTUBE_TOKEN_JSON")
        if not token:
            raise RuntimeError("Missing YOUTUBE_TOKEN_JSON; complete official OAuth consent.")
        creds = Credentials.from_authorized_user_info(json.loads(token), SCOPES)
        if not creds.valid:
            raise RuntimeError("YouTube OAuth token invalid/expired; refresh through official OAuth.")
        yt = build("youtube","v3",credentials=creds,cache_discovery=False)
        title = (info.get("title") or "Creative Commons short video")[:100]
        author = info.get("uploader") or info.get("channel") or "Original creator"
        description = (
            f"Source: {info['webpage_url']}\n"
            f"Creator: {author}\n"
            "License reported by source metadata: Creative Commons. Verify the exact license terms and attribution before relying on this upload."
        )
        body = {"snippet":{"title":title,"description":description,"categoryId":"22","tags":["Shorts","Creative Commons"]},"status":{"privacyStatus":"public"}}
        req = yt.videos().insert(part="snippet,status",body=body,media_body=MediaFileUpload(str(output),mimetype="video/mp4",resumable=True))
        response = None
        while response is None:
            _, response = req.next_chunk()
        print("Uploaded public video; ID:",response.get("id"))
    finally:
        shutil.rmtree(TEMP,ignore_errors=True)
        for p in ROOT.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".mp4",".part",".ytdl"}:
                try: p.unlink()
                except OSError: pass

if __name__ == "__main__":
    main()
