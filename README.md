# Get YouTube Transcript 🎬📝

Paste a YouTube link, get the transcript saved as a text file. That's it.

## How to use (the easy way)

1. **Double-click `get_transcript.bat`**
2. **Paste** your YouTube link and press **Enter**
3. Done! Look inside the **`transcripts`** folder — you'll find a folder named after the video, with the transcript file(s) in it.

> First time only: install [Python](https://www.python.org/downloads/) (tick **Add python.exe to PATH**), then run once in PowerShell:
> ```
> pip install -r requirements.txt
> ```

## What you get

- A folder per video: `transcripts/<video title> - <channel>/`
- The video's **main transcript**, with the language in the filename, e.g. `English [en] (default) (auto-generated).txt`
- If the video's main language **isn't English**, you automatically get the **English version too**
- Each file has the full text plus a version with timestamps

## PowerShell way (optional)

```
python get_transcript.py "https://www.youtube.com/watch?v=WXh4LF3zJ1Q"
```

## Files in this repo

- `get_transcript.bat` — double-click this to run the app
- `get_transcript.py` — the app itself
- `youtube_transcript_api/` — the transcript library (included here, v1.2.4)
- `transcripts/` — where your transcripts go
- `requirements.txt` — things to install once (`requests`, `defusedxml`)
