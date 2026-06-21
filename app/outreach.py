"""
outreach.py
Find likely contacts for a job and draft a cold email. Uses free heuristics
(email pattern guessing, LinkedIn search URLs) and optional Hunter.io free tier
(25 searches/month) if HUNTER_API_KEY is set.
"""

import json
import os
import re
from urllib.parse import quote

import requests

from db import get_connection, now
import llm

COMMON_EMAIL_PATTERNS = [
    "{first}.{last}@{domain}",
    "{first}{last}@{domain}",
    "{f}{last}@{domain}",
    "{first}@{domain}",
    "{last}@{domain}",
    "recruiting@{domain}",
    "careers@{domain}",
    "talent@{domain}",
    "hr@{domain}",
]


def _clean_domain(company: str, url: str = None):
    if url:
        m = re.search(r"https?://(?:www\.)?([^/]+)", url)
        if m:
            host = m.group(1).lower()
            if not any(x in host for x in ("linkedin.com", "indeed.com", "greenhouse.io", "lever.co")):
                return host.replace("www.", "")
    if not company:
        return None
    slug = re.sub(r"[^a-z0-9]", "", company.lower())
    if slug:
        return f"{slug}.com"
    return None


def guess_emails(first_name: str, last_name: str, domain: str):
    if not domain:
        return []
    first = first_name.lower().strip()
    last = last_name.lower().strip()
    f = first[:1] if first else ""
    emails = []
    for pat in COMMON_EMAIL_PATTERNS:
        addr = pat.format(first=first, last=last, f=f, domain=domain)
        if addr and addr not in emails:
            emails.append(addr)
    return emails


def hunter_domain_search(domain: str):
    """Optional: Hunter.io free tier (25 searches/month)."""
    api_key = os.environ.get("HUNTER_API_KEY")
    if not api_key or not domain:
        return []

    try:
        resp = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": api_key, "limit": 5},
            timeout=15,
        )
        resp.raise_for_status()
        emails = []
        for e in resp.json().get("data", {}).get("emails", []):
            emails.append({
                "email": e.get("value"),
                "name": f"{e.get('first_name', '')} {e.get('last_name', '')}".strip(),
                "title": e.get("position"),
                "confidence": e.get("confidence"),
                "source": "hunter",
            })
        return emails
    except requests.RequestException:
        return []


def linkedin_people_search(company: str, title_hint: str = "recruiter"):
    q = quote(f"{title_hint} {company}")
    return f"https://www.linkedin.com/search/results/people/?keywords={q}"


def find_contacts(company: str, job_url: str = None, your_first: str = "", your_last: str = ""):
    domain = _clean_domain(company, job_url)
    contacts = []

    for email in hunter_domain_search(domain):
        contacts.append(email)

    if domain:
        for email in guess_emails(your_first, your_last, domain)[:3]:
            contacts.append({"email": email, "name": None, "title": "pattern guess", "source": "pattern"})

    contacts.append({
        "email": None,
        "name": "LinkedIn search",
        "title": f"Find {company} recruiters / hiring managers",
        "linkedin_url": linkedin_people_search(company),
        "source": "linkedin",
    })

    return {"domain": domain, "contacts": contacts}


def generate_cold_email(jd_text: str, resume_markdown: str, contact_name: str = None, contact_title: str = None, preferences: list = None):
    return llm.generate_cold_email(
        jd_text, resume_markdown, contact_name, contact_title, preferences or []
    )


def save_outreach(jd_id: int, subject: str, body: str, contact_name: str = None, contact_email: str = None, contact_title: str = None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO outreach_messages
           (job_description_id, contact_name, contact_email, contact_title, subject, body, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (jd_id, contact_name, contact_email, contact_title, subject, body, now()),
    )
    msg_id = cur.lastrowid
    conn.commit()
    conn.close()
    return msg_id


def list_outreach(jd_id: int = None):
    conn = get_connection()
    if jd_id:
        rows = conn.execute(
            "SELECT * FROM outreach_messages WHERE job_description_id = ? ORDER BY created_at DESC",
            (jd_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM outreach_messages ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
