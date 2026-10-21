# ytdl — local YouTube downloader

A small localhost web UI that downloads YouTube videos with [yt-dlp](https://github.com/yt-dlp/yt-dlp). Paste a URL, pick a quality preset, watch progress, then save the file from `downloads/`.

## Requirements

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) on your `PATH` (needed to merge video+audio or extract audio)
- Network access to YouTube

## Setup

```bash
cd ytdl
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Confirm tools:

```bash
yt-dlp --version
ffmpeg -version
```

If `yt-dlp` is not on your PATH after install, use the venv’s copy (`which yt-dlp` while activated) or `python -m yt_dlp`.

## Run

```bash
cd ytdl
source .venv/bin/activate
python app.py
```

Open **http://127.0.0.1:8765**

The server binds to `127.0.0.1` only (not the LAN). No login is required.

Downloads are written to `ytdl/downloads/` and can also be saved from the UI when a job finishes.

## Quality presets

| Preset | Behavior |
|--------|----------|
| Best available | Best video + best audio (merged when needed) |
| Up to 1080p / 720p / 480p | Cap height; still merges A/V when separate |
| Audio only | Extract m4a via ffmpeg |

## Notes

- Single-video URLs only (`noplaylist`).
- Job status lives in memory for this process — restarting the server clears active jobs (files on disk remain).
- This is a local MVP, not a public download service. Do not expose the port beyond your machine.
- If YouTube returns “Sign in to confirm you’re not a bot”, export cookies from your browser into `ytdl/cookies.txt` (Netscape format) and restart the app. See [yt-dlp cookies FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp).
- A Node or Deno binary on `PATH` helps with newer YouTube extractions; the app enables `node` or `deno` automatically when found.
