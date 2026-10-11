#!/usr/bin/env python3
"""
YouTube Transcript Downloader

Asks for a YouTube link, then saves the transcript(s) to:
    transcripts/<VIDEO_TITLE> - <UPLOADED_BY>/<Language> [<code>] [(default)] [(auto-generated)].txt

Behavior (all automatic):
  - Creates a folder named "VIDEO_TITLE - UPLOADED_BY" (sanitized for Windows).
  - Detects the video's default transcript language via YouTube's
    defaultTranslationSourceTrackIndices / defaultAudioTrackIndex.
  - Saves the default transcript, filename includes the language and "(default)".
  - If default is not English, also saves English (direct EN track preferred,
    else translated via transcript.translate('en')).
  - File content matches the previous manual output:
    header + FULL TEXT + TIMESTAMPED sections.

Requires:
    pip install -r requirements.txt
    (the transcript library itself is vendored in ./youtube_transcript_api,
    so it is imported from this repo, not from PyPI)
Run (double-click get_transcript.bat, or):
    python get_transcript.py
    python get_transcript.py "https://www.youtube.com/watch?v=CsSnSBCVoDU"
"""

import re
import sys
from pathlib import Path

import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    VideoUnplayable,
    AgeRestricted,
    InvalidVideoId,
)


# ---------------------------------------------------------------- helpers

APP_DIR = Path(__file__).resolve().parent
DEFAULT_OUT_ROOT = APP_DIR / "transcripts"

INVALID_CHARS = r'<>:"/\\|?*\x00-\x1f'


def sanitize_filename(name: str, max_len: int = 100) -> str:
    """Make a string safe for Windows file/folder names."""
    name = re.sub(f"[{INVALID_CHARS}]", "_", name)
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    if not name:
        return "untitled"
    if len(name) > max_len:
        name = name[:max_len].rstrip()
    return name


def extract_video_id(url: str) -> str:
    """Extract the 11-char video id from most YouTube URL forms."""
    url = url.strip()
    patterns = [
        r"(?:v=|/v/|/embed/|/shorts/|/live/|youtu\.be/|/watch\?.*v=)([A-Za-z0-9_-]{11})",
        r"^([A-Za-z0-9_-]{11})$",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    raise ValueError(f"Could not extract video id from: {url}")


def get_video_metadata(video_id: str) -> tuple[str, str]:
    """Return (title, uploader) via oEmbed. Falls back to video_id."""
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    endpoints = [
        f"https://www.youtube.com/oembed?url={watch_url}&format=json",
        f"https://noembed.com/embed?url={watch_url}",
    ]
    for ep in endpoints:
        try:
            r = requests.get(ep, timeout=15)
            if r.status_code == 200:
                data = r.json()
                title = data.get("title", "").strip() or video_id
                uploader = data.get("author_name", "").strip() or "Unknown"
                return title, uploader
        except Exception:
            continue
    return video_id, "Unknown"


def format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def build_content(title, uploader, url, video_id, fetched, is_default: bool) -> str:
    full_text = " ".join(
        s.text.replace("\n", " ").strip() for s in fetched
    )
    lines = [
        f"Title: {title}",
        f"Channel: {uploader}",
        f"Link: {url}",
        f"Video ID: {video_id}",
        f"Language: {fetched.language} ({fetched.language_code}), "
        f"auto-generated: {fetched.is_generated}, default: {is_default}",
        f"Snippets: {len(fetched)}",
        "",
        "=== FULL TEXT ===",
        "",
        full_text,
        "",
        "",
        "=== TIMESTAMPED ===",
        "",
    ]
    for s in fetched:
        clean = s.text.replace("\n", " ").strip()
        lines.append(f"[{format_timestamp(s.start)}] {clean}")
    return "\n".join(lines)


def base_language_name(language: str) -> str:
    """Strip the library's ' (auto-generated)' suffix for cleaner filenames."""
    return language.replace("(auto-generated)", "").replace("  ", " ").strip()


def build_filename(fetched, is_default: bool, translated_from: str = "") -> str:
    base = sanitize_filename(base_language_name(fetched.language), max_len=60)
    code = re.sub(r"[^A-Za-z0-9_-]", "_", fetched.language_code)
    name = f"{base} [{code}]"
    if is_default:
        name += " (default)"
    if translated_from:
        name += f" (translated from {translated_from})"
    elif fetched.is_generated:
        name += " (auto-generated)"
    return sanitize_filename(name, max_len=120) + ".txt"


def get_default_language_code(ytt: YouTubeTranscriptApi, video_id: str,
                              transcript_list) -> str:
    """Detect the video's default caption language.

    Uses YouTube's defaultTranslationSourceTrackIndices / defaultAudioTrackIndex
    (the same innertube data the transcript library parses). Falls back to
    manual-first / English-first / first-available.
    """
    # 1) Try the real YouTube default indices via the library's fetcher.
    try:
        from youtube_transcript_api._transcripts import TranscriptListFetcher
        from youtube_transcript_api._settings import (
            INNERTUBE_CONTEXT, INNERTUBE_API_URL,
        )
        import re as _re
        from html import unescape as _unescape

        session = getattr(ytt, "_http_client", None) or requests.Session()
        fetcher = TranscriptListFetcher(session, getattr(ytt, "_proxy_config", None))
        try:
            caps = fetcher._fetch_captions_json(video_id)
        except Exception:
            caps = None
        if caps:
            tracks = caps.get("captionTracks", [])
            # Preferred: default translation source == original language.
            idxs = caps.get("defaultTranslationSourceTrackIndices") or []
            if idxs and 0 <= idxs[0] < len(tracks):
                return tracks[idxs[0]].get("languageCode", "")
            # Fallback: default audio track -> language prefix.
            audio_idx = caps.get("defaultAudioTrackIndex")
            audios = caps.get("audioTracks", [])
            if audio_idx is not None and 0 <= audio_idx < len(audios):
                audio_id = audios[audio_idx].get("audioTrackId", "")
                prefix = _re.split(r"[.\-_]", audio_id)[0].lower()  # e.g. en-US -> en
                short = prefix.split("-")[0]
                codes = {t.language_code for t in transcript_list}
                if short in codes:
                    return short
                for c in codes:
                    if c.lower().startswith(short) or short.startswith(c.lower()):
                        return c
    except Exception:
        pass

    # 2) Heuristic fallback: manual first, else English, else first.
    available = list(transcript_list)
    for t in available:
        if not t.is_generated:
            return t.language_code
    for t in available:
        if t.language_code.lower().startswith("en"):
            return t.language_code
    if available:
        return available[0].language_code
    return "en"


def pick_transcripts(ytt: YouTubeTranscriptApi, video_id: str):
    """Return (transcript_list, [(Transcript|translated, is_default, translated_from)])."""
    transcript_list = ytt.list(video_id)
    available = list(transcript_list)
    if not available:
        raise NoTranscriptFound(video_id, [], transcript_list)

    default_code = get_default_language_code(ytt, video_id, transcript_list)
    try:
        default_t = transcript_list.find_transcript([default_code])
    except Exception:
        # default code has no track (rare) -> first manual, else first available
        try:
            manual_codes = [t.language_code for t in available if not t.is_generated]
            default_t = transcript_list.find_manually_created_transcript(manual_codes)
        except Exception:
            default_t = available[0]
        default_code = default_t.language_code

    picks = [(default_t, True, "")]
    if default_t.language_code.lower().startswith("en"):
        return transcript_list, picks

    # Default is not English -> also fetch English.
    try:
        en_t = transcript_list.find_transcript(["en"])
        picks.append((en_t, False, ""))
        return transcript_list, picks
    except Exception:
        pass
    # No direct English track: translate the default transcript if possible.
    try:
        if default_t.is_translatable:
            translated = default_t.translate("en")
            picks.append((translated, False, default_t.language_code))
            return transcript_list, picks
    except Exception:
        pass
    return transcript_list, picks


# ---------------------------------------------------------------- main

def download_from_link(link: str, out_root: Path | None = None) -> list[Path]:
    if out_root is None:
        out_root = DEFAULT_OUT_ROOT
    video_id = extract_video_id(link)
    url = f"https://www.youtube.com/watch?v={video_id}"
    title, uploader = get_video_metadata(video_id)

    folder = out_root / sanitize_filename(f"{title} - {uploader}", max_len=150)
    folder.mkdir(parents=True, exist_ok=True)

    ytt = YouTubeTranscriptApi()
    _, picks = pick_transcripts(ytt, video_id)

    saved: list[Path] = []
    for transcript_obj, is_default, translated_from in picks:
        fetched = transcript_obj.fetch()
        filename = build_filename(fetched, is_default, translated_from)
        path = folder / filename
        path.write_text(
            build_content(title, uploader, url, video_id, fetched, is_default),
            encoding="utf-8",
        )
        saved.append(path)
        tag = "default" if is_default else (
            f"English (translated from {translated_from})" if translated_from
            else "English (extra)"
        )
        print(f"Saved [{tag}] {fetched.language} -> {path}")
    return saved


def pause_before_exit() -> None:
    """Keep the window open when double-clicked so results/errors can be read."""
    try:
        if sys.stdin.isatty():
            input("\nPress Enter to exit...")
    except (EOFError, KeyboardInterrupt):
        pass


def main() -> int:
    prompted = len(sys.argv) <= 1
    if not prompted:
        link = sys.argv[1].strip().strip('"').strip("'")
    else:
        try:
            link = input("Paste YouTube link: ").strip().strip('"').strip("'")
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 1
    if not link:
        print("No link provided.")
        pause_before_exit()
        return 1
    try:
        saved = download_from_link(link)
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        print(f"No transcripts available: {e}")
        pause_before_exit()
        return 2
    except (VideoUnavailable, VideoUnplayable, AgeRestricted, InvalidVideoId) as e:
        print(f"Video error: {e}")
        pause_before_exit()
        return 3
    except ValueError as e:
        print(str(e))
        pause_before_exit()
        return 4
    except Exception as e:
        print(f"Failed: {type(e).__name__}: {e}")
        pause_before_exit()
        return 5
    print(f"\nDone. {len(saved)} file(s) in folder.")
    for p in saved:
        print(f" - {p}")
    if prompted:
        pause_before_exit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
