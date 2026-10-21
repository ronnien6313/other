#!/usr/bin/env python3
"""Local YouTube downloader UI backed by yt-dlp."""

from __future__ import annotations

import re
import shutil
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory
from yt_dlp import YoutubeDL

APP_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = APP_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

HOST = "127.0.0.1"
PORT = 8765

# In-memory job status for this local process only.
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()

URL_RE = re.compile(
    r"^https?://(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/",
    re.IGNORECASE,
)

FORMAT_PRESETS = {
    "best": "bv*+ba/b",
    "1080p": "bv*[height<=1080]+ba/b[height<=1080]/b",
    "720p": "bv*[height<=720]+ba/b[height<=720]/b",
    "480p": "bv*[height<=480]+ba/b[height<=480]/b",
    "audio": "ba/b",
}

app = Flask(__name__)


def _set_job(job_id: str, **fields) -> None:
    with jobs_lock:
        job = jobs.setdefault(job_id, {"id": job_id})
        job.update(fields)


def _get_job(job_id: str) -> dict | None:
    with jobs_lock:
        job = jobs.get(job_id)
        return dict(job) if job else None


def _progress_hook(job_id: str):
    def hook(d: dict) -> None:
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            percent = round(100.0 * downloaded / total, 1) if total else None
            _set_job(
                job_id,
                status="downloading",
                percent=percent,
                speed=d.get("_speed_str") or d.get("speed"),
                eta=d.get("_eta_str") or d.get("eta"),
                filename=Path(d.get("filename") or "").name or None,
                message=d.get("_percent_str") or "Downloading…",
            )
        elif status == "finished":
            _set_job(
                job_id,
                status="processing",
                percent=100,
                message="Download finished; post-processing…",
                filename=Path(d.get("filename") or "").name or None,
            )
        elif status == "error":
            _set_job(job_id, status="error", message="yt-dlp reported an error")

    return hook


def _run_download(job_id: str, url: str, preset: str) -> None:
    format_selector = FORMAT_PRESETS.get(preset, FORMAT_PRESETS["best"])
    outtmpl = str(DOWNLOAD_DIR / "%(title).200B [%(id)s].%(ext)s")

    ydl_opts = {
        "format": format_selector,
        "outtmpl": outtmpl,
        "noplaylist": True,
        "progress_hooks": [_progress_hook(job_id)],
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        "fragment_retries": 3,
        "merge_output_format": "mp4" if preset != "audio" else None,
        "postprocessors": (
            [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "m4a",
                    "preferredquality": "192",
                }
            ]
            if preset == "audio"
            else []
        ),
    }
    # Prefer a JS runtime when available (YouTube extractor increasingly needs one).
    for runtime in ("node", "deno"):
        if shutil.which(runtime):
            ydl_opts["js_runtimes"] = {runtime: {}}
            break
    # Optional Netscape cookies file for bot / age challenges on restricted networks.
    cookies = APP_DIR / "cookies.txt"
    if cookies.is_file():
        ydl_opts["cookiefile"] = str(cookies)
    # Drop None values yt-dlp does not want.
    ydl_opts = {k: v for k, v in ydl_opts.items() if v is not None}

    _set_job(job_id, status="starting", percent=0, message="Starting download…", url=url)

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                raise RuntimeError("No video information returned")

            # Prefer the final merged/post-processed path when present.
            filepath = None
            requested = info.get("requested_downloads") or []
            if requested:
                filepath = requested[0].get("filepath")
            if not filepath:
                filepath = ydl.prepare_filename(info)
                if preset == "audio":
                    filepath = str(Path(filepath).with_suffix(".m4a"))

            name = Path(filepath).name if filepath else (info.get("title") or "download")
            _set_job(
                job_id,
                status="done",
                percent=100,
                message="Done",
                title=info.get("title"),
                filename=name,
                download_path=f"/files/{name}" if name else None,
            )
    except Exception as exc:  # noqa: BLE001 — surface any yt-dlp failure to the UI
        _set_job(job_id, status="error", message=str(exc), percent=None)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "host": HOST, "port": PORT})


@app.post("/api/download")
def start_download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    preset = (data.get("format") or "best").strip().lower()

    if not url or not URL_RE.match(url):
        return jsonify({"error": "Paste a valid YouTube URL (youtube.com or youtu.be)."}), 400
    if preset not in FORMAT_PRESETS:
        return jsonify({"error": f"Unknown format. Choose one of: {', '.join(FORMAT_PRESETS)}"}), 400

    job_id = uuid.uuid4().hex
    _set_job(
        job_id,
        status="queued",
        percent=0,
        message="Queued",
        url=url,
        format=preset,
        title=None,
        filename=None,
        download_path=None,
        speed=None,
        eta=None,
    )
    thread = threading.Thread(target=_run_download, args=(job_id, url, preset), daemon=True)
    thread.start()
    return jsonify({"job_id": job_id})


@app.get("/api/status/<job_id>")
def job_status(job_id: str):
    job = _get_job(job_id)
    if not job:
        return jsonify({"error": "Unknown job"}), 404
    return jsonify(job)


@app.get("/files/<path:filename>")
def serve_file(filename: str):
    # Only serve files that actually live in DOWNLOAD_DIR (no path traversal).
    safe = Path(filename).name
    path = DOWNLOAD_DIR / safe
    if not path.is_file():
        return jsonify({"error": "File not found"}), 404
    return send_from_directory(DOWNLOAD_DIR, safe, as_attachment=True)


def main() -> None:
    print(f"ytdl listening on http://{HOST}:{PORT} (localhost only)")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
