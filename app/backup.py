"""
backup.py
Streamlit Cloud wipes the local filesystem on restarts/redeploys, so the
SQLite file can't just live there. This module pushes the DB file to a
private GitHub repo after writes, and pulls it down on startup if a local
copy doesn't already exist.

Uses the GitHub REST API directly (no git CLI dependency, works fine in
Streamlit Cloud's restricted environment). Requires:
  - GITHUB_TOKEN: a fine-grained personal access token with read/write
    access to ONE private repo (just this backup repo, nothing else).
  - GITHUB_REPO: "yourusername/career-copilot-data"
  - GITHUB_BRANCH: defaults to "main"
"""

import os
import base64
import requests

GITHUB_API = "https://api.github.com"


def _config():
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO")
    branch = os.environ.get("GITHUB_BRANCH", "main")
    if not token or not repo:
        return None
    return {"token": token, "repo": repo, "branch": branch}


def _headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }


def backup_db(db_path: str, remote_path: str = "career.db"):
    """Push the current SQLite file to GitHub. Safe to call after every write;
    skips silently if GitHub isn't configured (e.g. local dev)."""
    cfg = _config()
    if cfg is None:
        return False, "GitHub backup not configured, skipping (this is fine for local dev)."

    with open(db_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()

    url = f"{GITHUB_API}/repos/{cfg['repo']}/contents/{remote_path}"
    headers = _headers(cfg["token"])

    # need the existing file's sha to update it, GitHub's API requires this
    existing = requests.get(url, headers=headers, params={"ref": cfg["branch"]})
    sha = existing.json().get("sha") if existing.status_code == 200 else None

    payload = {
        "message": "auto-backup career.db",
        "content": content_b64,
        "branch": cfg["branch"],
    }
    if sha:
        payload["sha"] = sha

    resp = requests.put(url, headers=headers, json=payload)
    if resp.status_code in (200, 201):
        return True, "Backed up successfully."
    return False, f"Backup failed: {resp.status_code} {resp.text[:300]}"


def restore_db(db_path: str, remote_path: str = "career.db"):
    """Pull the SQLite file down from GitHub if no local copy exists yet.
    Call this once at app startup, before db.init_db()."""
    if os.path.exists(db_path):
        return False, "Local DB already exists, skipping restore."

    cfg = _config()
    if cfg is None:
        return False, "GitHub backup not configured, starting with a fresh local DB."

    url = f"{GITHUB_API}/repos/{cfg['repo']}/contents/{remote_path}"
    headers = _headers(cfg["token"])
    resp = requests.get(url, headers=headers, params={"ref": cfg["branch"]})

    if resp.status_code != 200:
        return False, "No existing backup found on GitHub, starting fresh."

    content_b64 = resp.json()["content"]
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with open(db_path, "wb") as f:
        f.write(base64.b64decode(content_b64))
    return True, "Restored DB from GitHub backup."
