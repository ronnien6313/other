(() => {
  const form = document.getElementById("form");
  const urlInput = document.getElementById("url");
  const formatSelect = document.getElementById("format");
  const submitBtn = document.getElementById("submit");
  const statusEl = document.getElementById("status");
  const labelEl = document.getElementById("status-label");
  const pctEl = document.getElementById("status-pct");
  const msgEl = document.getElementById("status-msg");
  const metaEl = document.getElementById("status-meta");
  const barFill = document.getElementById("bar-fill");
  const fileLink = document.getElementById("file-link");

  let pollTimer = null;

  function stopPoll() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function setBusy(busy) {
    submitBtn.disabled = busy;
    urlInput.disabled = busy;
    formatSelect.disabled = busy;
    submitBtn.textContent = busy ? "Downloading…" : "Download";
  }

  function showStatus(job) {
    statusEl.hidden = false;
    statusEl.classList.remove("error", "done");
    if (job.status === "error") statusEl.classList.add("error");
    if (job.status === "done") statusEl.classList.add("done");

    const labels = {
      queued: "Queued",
      starting: "Starting",
      downloading: "Downloading",
      processing: "Processing",
      done: "Done",
      error: "Error",
    };
    labelEl.textContent = labels[job.status] || job.status || "Working";

    if (typeof job.percent === "number") {
      pctEl.textContent = `${job.percent}%`;
      barFill.style.width = `${Math.max(0, Math.min(100, job.percent))}%`;
    } else {
      pctEl.textContent = "";
      if (job.status === "downloading" || job.status === "starting") {
        barFill.style.width = "15%";
      }
    }

    msgEl.textContent = job.message || "";
    const bits = [];
    if (job.title) bits.push(job.title);
    if (job.filename) bits.push(job.filename);
    if (job.speed) bits.push(String(job.speed));
    if (job.eta) bits.push(`ETA ${job.eta}`);
    metaEl.textContent = bits.join(" · ");

    if (job.status === "done" && job.download_path) {
      fileLink.hidden = false;
      fileLink.href = job.download_path;
      fileLink.download = job.filename || "download";
      fileLink.textContent = `Save ${job.filename || "file"}`;
    } else {
      fileLink.hidden = true;
      fileLink.removeAttribute("href");
    }
  }

  async function poll(jobId) {
    try {
      const res = await fetch(`/api/status/${jobId}`);
      const job = await res.json();
      if (!res.ok) throw new Error(job.error || "Status check failed");
      showStatus(job);
      if (job.status === "done" || job.status === "error") {
        stopPoll();
        setBusy(false);
      }
    } catch (err) {
      stopPoll();
      setBusy(false);
      showStatus({
        status: "error",
        message: err.message || "Lost connection to the local server",
        percent: null,
      });
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    stopPoll();
    fileLink.hidden = true;

    const url = urlInput.value.trim();
    const format = formatSelect.value;

    setBusy(true);
    showStatus({
      status: "queued",
      message: "Sending request…",
      percent: 0,
    });

    try {
      const res = await fetch("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, format }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not start download");

      pollTimer = setInterval(() => poll(data.job_id), 700);
      poll(data.job_id);
    } catch (err) {
      setBusy(false);
      showStatus({
        status: "error",
        message: err.message || "Request failed",
        percent: null,
      });
    }
  });
})();
