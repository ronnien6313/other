"""Lightweight checks that do not hit YouTube."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import app as ytdl_app


def test_rejects_non_youtube_url():
    client = ytdl_app.app.test_client()
    res = client.post("/api/download", json={"url": "https://example.com/x", "format": "best"})
    assert res.status_code == 400
    assert "YouTube" in res.get_json()["error"]


def test_health():
    client = ytdl_app.app.test_client()
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.get_json()["ok"] is True


def test_download_job_success_mocked(tmp_path, monkeypatch):
    monkeypatch.setattr(ytdl_app, "DOWNLOAD_DIR", tmp_path)
    fake_file = tmp_path / "clip [abc123].mp4"
    fake_file.write_bytes(b"fake")

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=True):
            for hook in self.opts.get("progress_hooks", []):
                hook(
                    {
                        "status": "downloading",
                        "downloaded_bytes": 50,
                        "total_bytes": 100,
                        "filename": str(fake_file),
                        "_percent_str": "50.0%",
                    }
                )
                hook({"status": "finished", "filename": str(fake_file)})
            return {
                "title": "clip",
                "id": "abc123",
                "requested_downloads": [{"filepath": str(fake_file)}],
            }

        def prepare_filename(self, info):
            return str(fake_file)

    done = threading.Event()
    original_set = ytdl_app._set_job

    def set_and_signal(job_id, **fields):
        original_set(job_id, **fields)
        if fields.get("status") in {"done", "error"}:
            done.set()

    monkeypatch.setattr(ytdl_app, "_set_job", set_and_signal)

    client = ytdl_app.app.test_client()
    with patch.object(ytdl_app, "YoutubeDL", FakeYDL):
        res = client.post(
            "/api/download",
            json={"url": "https://www.youtube.com/watch?v=abc123", "format": "720p"},
        )
        assert res.status_code == 200
        job_id = res.get_json()["job_id"]
        assert done.wait(timeout=5)

    status = client.get(f"/api/status/{job_id}").get_json()
    assert status["status"] == "done"
    assert status["filename"] == fake_file.name
    assert status["download_path"] == f"/files/{fake_file.name}"

    file_res = client.get(status["download_path"])
    assert file_res.status_code == 200
    assert file_res.data == b"fake"


if __name__ == "__main__":
    # Minimal runner without pytest dependency.
    failures = 0
    for name, fn in list(globals().items()):
        if not name.startswith("test_"):
            continue
        try:
            if name == "test_download_job_success_mocked":
                import tempfile

                with tempfile.TemporaryDirectory() as td:
                    class M:
                        @staticmethod
                        def setattr(obj, attr, value):
                            setattr(obj, attr, value)

                    test_download_job_success_mocked(Path(td), M())
            else:
                fn()
            print(f"ok  {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {name}: {exc}")
    raise SystemExit(failures)
