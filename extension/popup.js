/**
 * popup.js
 * Wires the popup buttons to the content script (extraction) and the
 * extension_api.py backend (sending). Settings are stored in
 * chrome.storage.local, set once per machine.
 */

const statusEl = document.getElementById("status");
const jobTextEl = document.getElementById("jobText");
let lastUrl = null;
let lastPlatform = "other";

function setStatus(msg, isError = false) {
  statusEl.textContent = msg;
  statusEl.style.color = isError ? "crimson" : "#444";
}

async function loadSettings() {
  const stored = await chrome.storage.local.get(["apiUrl", "apiToken"]);
  document.getElementById("apiUrl").value = stored.apiUrl || "http://localhost:8765";
  document.getElementById("apiToken").value = stored.apiToken || "";
}

document.getElementById("saveSettingsBtn").addEventListener("click", async () => {
  const apiUrl = document.getElementById("apiUrl").value.trim();
  const apiToken = document.getElementById("apiToken").value.trim();
  await chrome.storage.local.set({ apiUrl, apiToken });
  setStatus("Settings saved.");
});

document.getElementById("extractBtn").addEventListener("click", async () => {
  setStatus("Extracting...");
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    setStatus("No active tab found.", true);
    return;
  }
  try {
    const response = await chrome.tabs.sendMessage(tab.id, { type: "EXTRACT_JOB_TEXT" });
    if (response?.text) {
      jobTextEl.value = response.text;
      lastUrl = response.url;
      lastPlatform = response.platform;
      setStatus(`Extracted ${response.text.length} characters from ${response.platform}.`);
    } else {
      setStatus("Could not auto-extract on this page. Paste the job text manually below.", true);
    }
  } catch (err) {
    setStatus(
      "Could not reach this page's content script. Try refreshing the page, or paste the job text manually.",
      true
    );
  }
});

document.getElementById("sendBtn").addEventListener("click", async () => {
  const text = jobTextEl.value.trim();
  if (text.length < 30) {
    setStatus("Text looks too short, extract or paste the full job posting first.", true);
    return;
  }
  const { apiUrl, apiToken } = await chrome.storage.local.get(["apiUrl", "apiToken"]);
  if (!apiUrl) {
    setStatus("Set the API URL in Settings first.", true);
    return;
  }

  setStatus("Sending...");
  try {
    const resp = await fetch(`${apiUrl.replace(/\/$/, "")}/ingest_jd`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Token": apiToken || "",
      },
      body: JSON.stringify({
        text,
        url: lastUrl || null,
        platform: lastPlatform || "other",
      }),
    });
    if (!resp.ok) {
      const body = await resp.text();
      setStatus(`Server error (${resp.status}): ${body.slice(0, 150)}`, true);
      return;
    }
    const data = await resp.json();
    setStatus(`Sent. Job description id ${data.job_description_id}. Open Career Copilot to generate.`);
  } catch (err) {
    setStatus(`Could not reach API at ${apiUrl}. Is extension_api.py running?`, true);
  }
});

loadSettings();
