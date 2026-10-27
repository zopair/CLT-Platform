"""Process and upload only media owned by you or explicitly licensed for republication."""
import json, os, shutil, subprocess, tempfile
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from yt_dlp import YoutubeDL

ROOT = Path(__file__).resolve().parents[1]
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TEMP = Path(tempfile.mkdtemp(prefix="licensed-media-"))
CACHE = TEMP / "cache"
CACHE.mkdir(parents=True, exist_ok=True)

def main():
    try:
        urls = [x.strip() for x in os.environ.get("SOURCE_CHANNELS", "").splitlines() if x.strip()]
        if not urls:
            raise RuntimeError("Set SOURCE_CHANNELS to authorized source URLs.")
        opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True, "cachedir": str(CACHE)}
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(urls[0], download=False)
        if info and info.get("entries"):
            entries = sorted((e for e in info["entries"] if e), key=lambda e: str(e.get("upload_date") or ""), reverse=True)
            if not entries: raise RuntimeError("No eligible source videos found.")
            info = entries[0]
        if not info or not info.get("webpage_url"): raise RuntimeError("Could not resolve a source video.")
        download_opts = {"format":"bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best","merge_output_format":"mp4","outtmpl":str(TEMP/"source.%(ext)s"),"noplaylist":True,"quiet":True,"cachedir":str(CACHE)}
        with YoutubeDL(download_opts) as ydl: ydl.download([info["webpage_url"]])
        sources = [p for p in TEMP.glob("source*") if p.suffix.lower()==".mp4" and p.is_file()]
        if not sources: raise RuntimeError("Download did not produce MP4.")
        output = TEMP/"processed.mp4"
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=brightness=0.02:saturation=1.1"
        subprocess.run(["ffmpeg","-hide_banner","-y","-i",str(sources[0]),"-t","55","-vf",vf,"-c:v","libx264","-preset","medium","-crf","28","-pix_fmt","yuv420p","-c:a","aac","-b:a","128k","-movflags","+faststart",str(output)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        token = os.environ.get("YOUTUBE_TOKEN_JSON")
        if not token: raise RuntimeError("Missing YOUTUBE_TOKEN_JSON; complete official OAuth consent.")
        creds = Credentials.from_authorized_user_info(json.loads(token), SCOPES)
        if not creds.valid: raise RuntimeError("YouTube OAuth token invalid/expired; refresh through official OAuth.")
        yt = build("youtube","v3",credentials=creds,cache_discovery=False)
        title = (info.get("title") or "Licensed short video")[:100]
        body = {"snippet":{"title":title,"description":"Authorized source; verify license and attribution requirements.\nSource: "+info["webpage_url"],"categoryId":"22","tags":["Shorts"]},"status":{"privacyStatus":"private"}}
        req = yt.videos().insert(part="snippet,status",body=body,media_body=MediaFileUpload(str(output),mimetype="video/mp4",resumable=True))
        response = None
        while response is None: _, response = req.next_chunk()
        print("Uploaded private video for review; ID:",response.get("id"))
    finally:
        shutil.rmtree(TEMP,ignore_errors=True)
        for p in ROOT.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".mp4",".part",".ytdl"}:
                try: p.unlink()
                except OSError: pass

if __name__ == "__main__": main()
