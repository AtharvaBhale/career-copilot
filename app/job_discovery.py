"""
job_discovery.py
Fetch fresh job openings from free public APIs, filter for OPT-friendly
postings (Avisa-style heuristics), score fit against your profile, and
recommend which ones are worth applying to today.

Free sources (no API key required):
  - Remotive: https://remotive.com/api/remote-jobs
  - Arbeitnow: https://www.arbeitnow.com/api/job-board-api
  - RemoteOK: https://remoteok.com/api

Optional (free tier with registration):
  - Adzuna: set ADZUNA_APP_ID and ADZUNA_APP_KEY in secrets
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

from db import get_connection, now
import memory
import llm
import profile

# Phrases that usually block OPT / international candidates.
OPT_BLOCK_PATTERNS = [
    r"u\.?s\.?\s*citizen\s*(only|required|ship)",
    r"must\s+be\s+a?\s*u\.?s\.?\s*citizen",
    r"no\s+(visa\s+)?sponsorship",
    r"(unable|will\s+not|cannot|does\s+not)\s+sponsor",
    r"without\s+sponsorship\s+now\s+or\s+(in\s+the\s+)?future",
    r"authorized\s+to\s+work\s+without\s+sponsorship",
    r"only\s+u\.?s\.?\s*(persons|nationals|residents)",
    r"security\s+clearance\s+required",
    r"itar\s+restricted",
    r"green\s+card\s+required",
]

OPT_POSITIVE_PATTERNS = [
    r"opt\b",
    r"stem\s+opt",
    r"visa\s+sponsorship",
    r"h-?1b",
    r"e-?verify",
    r"international\s+students?",
    r"work\s+authorization",
    r"sponsor(ship)?\s+(available|provided|offered)",
]

TARGET_ROLE_KEYWORDS = [
    "data scientist", "data analyst", "data engineer", "machine learning",
    "software engineer", "systems engineer", "backend", "full stack",
    "business analyst", "analytics", "ml engineer", "python", "java",
    "project coordinator", "technical",
]


def _parse_date(value):
    """Parse API date fields that may be str, int (unix), or missing."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            ts = float(value)
            if ts > 1e12:  # milliseconds
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if not value:
        return None
    if value.isdigit():
        return _parse_date(int(value))

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    for fmt, length in (
        ("%Y-%m-%dT%H:%M:%S", 19),
        ("%Y-%m-%d %H:%M:%S", 19),
        ("%Y-%m-%d", 10),
    ):
        try:
            return datetime.strptime(value[:length], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _posted_at_label(value):
    dt = _parse_date(value)
    if dt:
        return dt.strftime("%Y-%m-%d")
    if value is not None:
        return str(value)[:10]
    return "unknown"


def _is_fresh(posted_at, max_age_days: int = 1):
    dt = _parse_date(posted_at)
    if dt is None:
        return True  # unknown date: keep but rank lower
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= cutoff


def assess_opt_friendliness(description: str, title: str = ""):
    text = f"{title}\n{description}".lower()
    blocked = []
    for pat in OPT_BLOCK_PATTERNS:
        if re.search(pat, text, re.I):
            blocked.append(pat.replace(r"\b", "").replace("\\", ""))

    positive = []
    for pat in OPT_POSITIVE_PATTERNS:
        if re.search(pat, text, re.I):
            positive.append(pat.replace(r"\b", "").replace("\\", ""))

    friendly = len(blocked) == 0
    return friendly, {"blocked_reasons": blocked, "positive_signals": positive}


def _role_relevance(title: str, description: str):
    text = f"{title} {description}".lower()
    hits = sum(1 for kw in TARGET_ROLE_KEYWORDS if kw in text)
    return min(100, hits * 15)


def fetch_remotive():
    jobs = []
    try:
        resp = requests.get("https://remotive.com/api/remote-jobs", timeout=20)
        resp.raise_for_status()
        for item in resp.json().get("jobs", []):
            jobs.append({
                "external_id": str(item.get("id", item.get("url", ""))),
                "source": "remotive",
                "company": item.get("company_name"),
                "title": item.get("title"),
                "location": item.get("candidate_required_location") or "Remote",
                "url": item.get("url"),
                "description": item.get("description") or "",
                "posted_at": item.get("publication_date"),
            })
    except requests.RequestException:
        pass
    return jobs


def fetch_arbeitnow():
    jobs = []
    try:
        resp = requests.get("https://www.arbeitnow.com/api/job-board-api", timeout=20)
        resp.raise_for_status()
        for item in resp.json().get("data", []):
            jobs.append({
                "external_id": item.get("slug") or str(item.get("url", "")),
                "source": "arbeitnow",
                "company": item.get("company_name"),
                "title": item.get("title"),
                "location": ", ".join(item.get("location") or []) or "Remote",
                "url": item.get("url"),
                "description": item.get("description") or "",
                "posted_at": item.get("created_at"),
            })
    except requests.RequestException:
        pass
    return jobs


def fetch_remoteok():
    jobs = []
    try:
        resp = requests.get(
            "https://remoteok.com/api",
            headers={"User-Agent": "CareerCopilot/1.0"},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        for item in data[1:] if isinstance(data, list) and len(data) > 1 else []:
            if not isinstance(item, dict):
                continue
            jobs.append({
                "external_id": str(item.get("id", item.get("url", ""))),
                "source": "remoteok",
                "company": item.get("company"),
                "title": item.get("position") or item.get("title"),
                "location": item.get("location") or "Remote",
                "url": item.get("url") or item.get("apply_url"),
                "description": item.get("description") or "",
                "posted_at": item.get("date"),
            })
    except requests.RequestException:
        pass
    return jobs


def fetch_adzuna():
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        return []

    jobs = []
    queries = ["data scientist", "software engineer", "data analyst"]
    for q in queries:
        try:
            url = (
                f"https://api.adzuna.com/v1/api/jobs/us/search/1"
                f"?app_id={app_id}&app_key={app_key}"
                f"&results_per_page=25&what={quote(q)}&max_days_old=1"
            )
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            for item in resp.json().get("results", []):
                jobs.append({
                    "external_id": item.get("id") or item.get("redirect_url", ""),
                    "source": "adzuna",
                    "company": (item.get("company") or {}).get("display_name"),
                    "title": item.get("title"),
                    "location": (item.get("location") or {}).get("display_name") or "USA",
                    "url": item.get("redirect_url"),
                    "description": item.get("description") or "",
                    "posted_at": item.get("created"),
                })
        except requests.RequestException:
            continue
    return jobs


def fetch_all_sources():
    seen = set()
    merged = []
    for fetcher in (fetch_remotive, fetch_arbeitnow, fetch_remoteok, fetch_adzuna):
        for job in fetcher():
            key = (job["source"], job["external_id"])
            if key in seen or not job.get("description"):
                continue
            seen.add(key)
            merged.append(job)
    return merged


def _profile_summary():
    items = memory.all_active_items()
    bullets = [i["content"] for i in items if i["item_type"] in ("bullet", "project", "skill", "summary")]
    header = profile.profile_summary_for_llm()
    body = "\n".join(f"- {b}" for b in bullets[:25])
    return f"{header}\n\nBackground:\n{body}"


def discover_jobs(max_age_days: int = 1, score_with_llm: bool = True, limit: int = 30):
    """
    Pull fresh jobs, filter OPT-unfriendly listings, score matches, store in DB.
    Returns list of newly inserted/updated job dicts.
    """
    raw_jobs = fetch_all_sources()
    profile = _profile_summary()
    conn = get_connection()
    cur = conn.cursor()
    results = []

    for job in raw_jobs:
        if not _is_fresh(job.get("posted_at"), max_age_days=max_age_days):
            continue

        opt_ok, opt_flags = assess_opt_friendliness(job["description"], job.get("title") or "")
        if not opt_ok:
            continue

        role_score = _role_relevance(job.get("title") or "", job["description"])
        match = {"match_score": role_score, "interview_likelihood": None, "recommendation": "maybe", "recommendation_reason": "Role keyword match only."}

        if score_with_llm and role_score >= 30 and profile.strip():
            jd_blob = f"{job.get('title')}\n{job.get('company')}\n{job['description'][:4000]}"
            try:
                match = llm.score_job_match(jd_blob, profile)
            except RuntimeError:
                match["recommendation_reason"] = "LLM scoring skipped (GROQ_API_KEY not set)."
        elif score_with_llm and not profile.strip():
            match["recommendation_reason"] = "Add career items on the Memory page for LLM scoring."

        cur.execute(
            """INSERT INTO discovered_jobs
               (external_id, source, company, title, location, url, description,
                posted_at, fetched_at, opt_friendly, opt_flags,
                match_score, interview_likelihood, recommendation, recommendation_reason, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
               ON CONFLICT(source, external_id) DO UPDATE SET
                 fetched_at=excluded.fetched_at,
                 match_score=excluded.match_score,
                 interview_likelihood=excluded.interview_likelihood,
                 recommendation=excluded.recommendation,
                 recommendation_reason=excluded.recommendation_reason""",
            (
                job["external_id"],
                job["source"],
                job.get("company"),
                job.get("title"),
                job.get("location"),
                job.get("url"),
                job["description"],
                _posted_at_label(job.get("posted_at")) if job.get("posted_at") is not None else None,
                now(),
                1 if opt_ok else 0,
                json.dumps(opt_flags),
                match.get("match_score"),
                match.get("interview_likelihood"),
                match.get("recommendation"),
                match.get("recommendation_reason"),
            ),
        )
        row = cur.execute(
            "SELECT * FROM discovered_jobs WHERE source = ? AND external_id = ?",
            (job["source"], job["external_id"]),
        ).fetchone()
        if row:
            results.append(dict(row))

        if len(results) >= limit:
            break

    conn.commit()
    conn.close()
    results.sort(key=lambda r: (r.get("recommendation") != "apply", -(r.get("match_score") or 0)))
    return results


def list_discovered_jobs(status: str = None, recommendation: str = None, limit: int = 50):
    conn = get_connection()
    query = "SELECT * FROM discovered_jobs WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if recommendation:
        query += " AND recommendation = ?"
        params.append(recommendation)
    query += " ORDER BY match_score DESC NULLS LAST, fetched_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_discovered_status(job_id: int, status: str):
    conn = get_connection()
    conn.execute("UPDATE discovered_jobs SET status = ? WHERE id = ?", (status, job_id))
    conn.commit()
    conn.close()


def import_to_jd(discovered_id: int):
    """Copy a discovered job into job_descriptions for the tailoring pipeline."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM discovered_jobs WHERE id = ?", (discovered_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError("Discovered job not found")

    raw = f"{row['title'] or ''} at {row['company'] or 'Unknown Company'}\n\n{row['description']}"
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO job_descriptions
           (company, title, raw_text, url, source_platform, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (row["company"], row["title"], raw, row["url"], row["source"], now()),
    )
    jd_id = cur.lastrowid
    cur.execute(
        "UPDATE discovered_jobs SET status = 'imported', job_description_id = ? WHERE id = ?",
        (jd_id, discovered_id),
    )
    conn.commit()
    conn.close()
    return jd_id, dict(row)
