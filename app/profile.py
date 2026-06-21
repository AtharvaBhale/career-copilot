"""
profile.py
Single-user profile stored in SQLite. Used to personalize resumes, outreach,
and job-match scoring. Designed for one user now; multi-user would add auth
and a user_id column on all tables.
"""

import json
from db import get_connection, now

DEFAULT_PROFILE = {
    "full_name": "Atharva Bhale",
    "first_name": "Atharva",
    "last_name": "Bhale",
    "email": "",
    "phone": "",
    "location": "Willimantic, CT",
    "linkedin_url": "",
    "target_roles": [
        "Data Scientist",
        "Software Engineer",
        "Data Analyst",
        "Systems Engineer",
        "Business Analyst",
        "ML Engineer",
    ],
    "work_auth_summary": (
        "F-1 OPT EAD holder, authorized to work now. "
        "STEM OPT eligible after Feb 2027. Future H-1B sponsorship needed for long-term stay."
    ),
}


def get_profile():
    conn = get_connection()
    row = conn.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
    conn.close()
    if row is None:
        return dict(DEFAULT_PROFILE)
    data = dict(row)
    try:
        data["target_roles"] = json.loads(data.get("target_roles") or "[]")
    except json.JSONDecodeError:
        data["target_roles"] = DEFAULT_PROFILE["target_roles"]
    return data


def save_profile(
    full_name: str,
    first_name: str,
    last_name: str,
    email: str = "",
    phone: str = "",
    location: str = "",
    linkedin_url: str = "",
    target_roles: list = None,
    work_auth_summary: str = "",
):
    conn = get_connection()
    conn.execute(
        """INSERT INTO user_profile
           (id, full_name, first_name, last_name, email, phone, location,
            linkedin_url, target_roles, work_auth_summary, updated_at)
           VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             full_name=excluded.full_name,
             first_name=excluded.first_name,
             last_name=excluded.last_name,
             email=excluded.email,
             phone=excluded.phone,
             location=excluded.location,
             linkedin_url=excluded.linkedin_url,
             target_roles=excluded.target_roles,
             work_auth_summary=excluded.work_auth_summary,
             updated_at=excluded.updated_at""",
        (
            full_name,
            first_name,
            last_name,
            email,
            phone,
            location,
            linkedin_url,
            json.dumps(target_roles or []),
            work_auth_summary,
            now(),
        ),
    )
    conn.commit()
    conn.close()


def is_configured():
    """True if user has saved a profile or has memory items."""
    conn = get_connection()
    has_profile = conn.execute("SELECT 1 FROM user_profile WHERE id = 1").fetchone() is not None
    memory_count = conn.execute("SELECT COUNT(*) as c FROM source_items WHERE active = 1").fetchone()["c"]
    conn.close()
    return has_profile and memory_count > 0


def profile_summary_for_llm():
    p = get_profile()
    roles = ", ".join(p.get("target_roles") or [])
    return (
        f"Name: {p.get('full_name')}\n"
        f"Location: {p.get('location')}\n"
        f"Target roles: {roles}\n"
        f"Work authorization: {p.get('work_auth_summary')}"
    )
