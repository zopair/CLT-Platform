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


def make_procedural_fallback(topic: str, duration: int) -> Path:
    """Render a standalone vertical text-motion Short using FFmpeg only."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is unavailable; cannot render procedural fallback.")
    duration = max(10, min(int(duration), 60))
    output = TEMP / "procedural-fallback.mp4"
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    if not Path(font).is_file():
        font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    cards = [
        ("fallback-hook.txt", "فكرة تستحق التفكير"),
        ("fallback-topic.txt", topic or "معلومة جديدة كل يوم"),
        ("fallback-cta.txt", "تابع للمزيد"),
    ]
    text_paths = []
    for filename, value in cards:
        path = TEMP / filename
        path.write_text(value.replace("\\x00", "")[:180], encoding="utf-8")
        text_paths.append(path)
    third = duration / 3
    filters = [
        "drawgrid=width=100:height=100:thickness=1:color=white@0.08",
        f"drawtext=fontfile={font}:textfile={text_paths[0]}:expansion=none:fontcolor=white:fontsize=66:x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=0x142033@0.85:boxborderw=38:text_shaping=1:enable='between(t\\,0\\,{third:.2f})'",
        f"drawtext=fontfile={font}:textfile={text_paths[1]}:expansion=none:fontcolor=0x7dd3fc:fontsize=58:x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=0x142033@0.88:boxborderw=38:text_shaping=1:enable='between(t\\,{third:.2f}\\,{2*third:.2f})'",
        f"drawtext=fontfile={font}:textfile={text_paths[2]}:expansion=none:fontcolor=white:fontsize=68:x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=0x142033@0.85:boxborderw=38:text_shaping=1:enable='gte(t\\,{2*third:.2f})'",
        f"drawbox=x=0:y=ih-22:w=iw*t/{duration}:h=22:color=0x38bdf8:t=fill",
    ]
    filter_graph = ",".join(filters)
    command = [
        ffmpeg, "-hide_banner", "-y",
        "-f", "lavfi", "-i", f"color=c=0x0b1220:s=1080x1920:r=30:d={duration}",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-vf", filter_graph, "-t", str(duration),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
        "-shortest", "-movflags", "+faststart", str(output),
    ]
    subprocess.run(command, check=True, timeout=300, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("Procedural FFmpeg fallback did not produce a valid MP4.")
    print(f"[fallback] Procedural FFmpeg video rendered: {output.stat().st_size} bytes")
    return output


def main():
    try:
        print("[1/5] Generating a new Short with PurffleShorts (MIT)...")
        topic = os.environ.get("SHORTS_TOPIC", "").strip()
        duration = int(os.environ.get("SHORTS_DURATION", "45"))
        generator_env = os.environ.copy()
        generator_env["OUTPUT_DIR"] = str(TEMP / "generated")
        generator_env["DATA_DIR"] = str(TEMP / "generator-data")
        generator_env["PURFFLE_HOME"] = str(TEMP / "purffle-home")
        generator_env["CHANNEL_NAME"] = "Alyzopair"
        command = [
            "purffle-shorts", "make",
            "--source", "niche",
            "--lang", os.environ.get("SHORTS_LANGUAGE", "ar"),
            "--duration", str(duration),
            "--aspect", "9:16",
            "--no-upload",
        ]
        if topic:
            command.extend(["--topic", topic])
        try:
            subprocess.run(command, check=True, env=generator_env, timeout=1500)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
            print(f"[fallback] Primary generation unavailable ({type(exc).__name__}); trying built-in offline demo.")
            try:
                subprocess.run(
                    ["purffle-shorts", "demo", "--style", "story"],
                    check=True, env=generator_env, timeout=1500,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as demo_exc:
                print(f"[fallback] Offline demo failed ({type(demo_exc).__name__}); using procedural FFmpeg renderer.")
        generated = [
            path for path in TEMP.rglob("*.mp4")
            if path.is_file() and path.stat().st_size > 0
            and path.name not in {"processed.mp4", "procedural-fallback.mp4"}
        ]
        info = {
            "title": topic or "Short generated by PurffleShorts",
            "webpage_url": "AI-generated original video",
            "uploader": "PurffleShorts",
            "description": "Original generated short-form video.",
        }
        if generated:
            generated.sort(key=lambda path: path.stat().st_mtime, reverse=True)
            source_video = generated[0]
            metadata_candidates = list(source_video.parent.glob("metadata.json"))
            if metadata_candidates:
                try:
                    metadata = json.loads(metadata_candidates[0].read_text(encoding="utf-8"))
                    info["title"] = metadata.get("title") or info["title"]
                    info["description"] = metadata.get("description") or info["description"]
                except (OSError, ValueError):
                    pass
            print(f"[1/5] Generated video: {source_video.name}")
        else:
            source_video = make_procedural_fallback(topic, duration)
            info["title"] = (topic or "فكرة تستحق التفكير")[:100]
            info["description"] = "Procedurally generated text-motion Short rendered locally with FFmpeg."
        print("[2/5] Generator output validated.")

        print("[3/5] Encoding vertical video with standard FFmpeg settings...")
        output = TEMP / "processed.mp4"
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-y", "-i", str(source_video), "-t", os.environ.get("SHORTS_DURATION", "45"),
                "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "28",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", str(output),
            ],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("FFmpeg completed without a usable output file.")
        print(f"[3/5] Processing succeeded: {output.name} ({output.stat().st_size} bytes)")

        token_json = os.environ.get("YOUTUBE_TOKEN_JSON", "").strip()
        refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()
        if token_json:
            creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
        elif refresh_token:
            client_id = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
            client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
            if not client_id or not client_secret:
                raise RuntimeError(
                    "YOUTUBE_REFRESH_TOKEN requires YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET "
                    "from the same Google OAuth client. No upload performed."
                )
            creds = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret,
                scopes=SCOPES,
            )
        else:
            raise RuntimeError(
                "Configure YOUTUBE_TOKEN_JSON or YOUTUBE_REFRESH_TOKEN plus OAuth client credentials. "
                "A refresh token must first be issued through Google's user-consent OAuth flow."
            )

        if not creds.valid:
            if creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
            else:
                raise RuntimeError(
                    "OAuth credentials are expired and have no refresh token. Re-authorize the intended channel."
                )

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
        description = info.get("description") or "Original AI-generated Short created with PurffleShorts."
        body = {
            "snippet": {
                "title": title, "description": description, "categoryId": "1",
                "tags": ["Shorts", "Animation"],
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": os.environ.get("YOUTUBE_MADE_FOR_KIDS", "false").strip().lower() == "true",
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
