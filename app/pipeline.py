"""
pipeline.py
The actual "JD in, tailored resume + cover letter + scores out" flow.
Everything in app.py and the extension receiver calls into this, so
there's exactly one place that defines what "generate for this JD" means.
"""

import json
from db import get_connection, now
import memory
import llm
from jd_parser import parse_jd


def ingest_job_description(raw_text: str, url: str = None, source_platform: str = None):
    """Parse and store a new JD. Returns the job_description_id and parsed fields."""
    parsed = parse_jd(raw_text, url=url, source_platform=source_platform)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO job_descriptions
           (company, title, raw_text, url, source_platform,
            parsed_requirements, parsed_responsibilities, parsed_preferred_skills, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            parsed.get("company"),
            parsed.get("title"),
            raw_text,
            url,
            source_platform,
            json.dumps(parsed.get("requirements", [])),
            json.dumps(parsed.get("responsibilities", [])),
            json.dumps(parsed.get("preferred_skills", [])),
            now(),
        ),
    )
    jd_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jd_id, parsed


def generate_for_job(jd_id: int, max_pages: int = 1):
    """
    Full pipeline for one job description:
    retrieve relevant memory -> generate resume -> truth-check ->
    skill gap -> ATS score -> generate cover letter.
    Returns a dict with everything, and persists the resume/cover letter rows.
    """
    conn = get_connection()
    jd_row = conn.execute(
        "SELECT * FROM job_descriptions WHERE id = ?", (jd_id,)
    ).fetchone()
    conn.close()
    if jd_row is None:
        raise ValueError(f"No job_description with id {jd_id}")
    jd_text = jd_row["raw_text"]

    preferences = memory.get_active_preferences()
    retrieved = memory.retrieve_relevant(
        jd_text, top_k=15, item_types=["bullet", "project", "skill", "cert", "summary"]
    )

    resume_md = llm.generate_resume(jd_text, retrieved, preferences, max_pages=max_pages)
    truth_result = llm.truth_check(resume_md, retrieved)
    gap_result = llm.skill_gap_analysis(jd_text, retrieved)
    ats_result = llm.ats_score(jd_text, resume_md)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO resume_versions
           (job_description_id, content_markdown, ats_score, truth_check_passed,
            truth_check_notes, skill_gap_notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            jd_id,
            resume_md,
            ats_result.get("score"),
            1 if truth_result.get("passed") else 0,
            json.dumps(truth_result.get("flagged_claims", [])),
            json.dumps(gap_result),
            now(),
        ),
    )
    resume_id = cur.lastrowid
    conn.commit()
    conn.close()

    cover_letter_md = llm.generate_cover_letter(jd_text, resume_md, preferences)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO cover_letters (job_description_id, resume_version_id, content, created_at)
           VALUES (?, ?, ?, ?)""",
        (jd_id, resume_id, cover_letter_md, now()),
    )
    cover_letter_id = cur.lastrowid
    conn.commit()
    conn.close()

    return {
        "jd_id": jd_id,
        "resume_id": resume_id,
        "cover_letter_id": cover_letter_id,
        "resume_markdown": resume_md,
        "cover_letter": cover_letter_md,
        "ats_score": ats_result,
        "truth_check": truth_result,
        "skill_gap": gap_result,
        "retrieved_count": len(retrieved),
    }


def save_user_edit(resume_id: int = None, cover_letter_id: int = None, final_text: str = None):
    conn = get_connection()
    if resume_id is not None:
        conn.execute(
            "UPDATE resume_versions SET user_edited_final = ? WHERE id = ?",
            (final_text, resume_id),
        )
    if cover_letter_id is not None:
        conn.execute(
            "UPDATE cover_letters SET user_edited_final = ? WHERE id = ?",
            (final_text, cover_letter_id),
        )
    conn.commit()
    conn.close()


def update_application_status(jd_id: int, resume_id: int, status: str, notes: str = "", priority: str = "medium"):
    conn = get_connection()
    cur = conn.cursor()
    existing = cur.execute(
        "SELECT id FROM applications WHERE job_description_id = ?", (jd_id,)
    ).fetchone()
    applied_at = now() if status == "applied" else None
    if existing:
        cur.execute(
            """UPDATE applications SET status = ?, notes = ?, priority = ?,
               applied_at = COALESCE(?, applied_at), updated_at = ? WHERE id = ?""",
            (status, notes, priority, applied_at, now(), existing["id"]),
        )
        app_id = existing["id"]
    else:
        cur.execute(
            """INSERT INTO applications
               (job_description_id, resume_version_id, status, notes, priority, applied_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (jd_id, resume_id, status, notes, priority, applied_at, now()),
        )
        app_id = cur.lastrowid
    conn.commit()
    conn.close()
    return app_id


def schedule_follow_up(application_id: int, due_date: str, follow_up_type: str = "email", notes: str = ""):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO follow_ups (application_id, due_date, follow_up_type, notes, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (application_id, due_date, follow_up_type, notes, now()),
    )
    fid = cur.lastrowid
    conn.commit()
    conn.close()
    return fid


def complete_follow_up(follow_up_id: int):
    conn = get_connection()
    conn.execute(
        "UPDATE follow_ups SET completed = 1, completed_at = ? WHERE id = ?",
        (now(), follow_up_id),
    )
    conn.commit()
    conn.close()


def add_networking_contact(name: str, company: str, title: str = "", email: str = "", linkedin_url: str = "",
                           relationship: str = "other", notes: str = "", application_id: int = None,
                           next_follow_up: str = None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO networking_contacts
           (name, company, title, email, linkedin_url, relationship, notes,
            application_id, last_contact, next_follow_up, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, company, title, email, linkedin_url, relationship, notes,
         application_id, now(), next_follow_up, now(), now()),
    )
    cid = cur.lastrowid
    conn.commit()
    conn.close()
    return cid


def create_interview_prep(application_id: int, jd_text: str, resume_markdown: str):
    prep = llm.generate_interview_prep(jd_text, resume_markdown)
    checklist = prep.get("checklist", [])
    checklist_items = [{"item": c.get("item", c) if isinstance(c, dict) else str(c), "done": False} for c in checklist]

    conn = get_connection()
    cur = conn.cursor()
    existing = cur.execute(
        "SELECT id FROM interview_prep WHERE application_id = ?", (application_id,)
    ).fetchone()
    payload = json.dumps({
        "checklist": checklist_items,
        "likely_questions": prep.get("likely_questions", []),
        "stories_to_prepare": prep.get("stories_to_prepare", []),
        "company_research": prep.get("company_research", []),
    })
    if existing:
        cur.execute(
            "UPDATE interview_prep SET checklist_json = ?, updated_at = ? WHERE id = ?",
            (payload, now(), existing["id"]),
        )
        prep_id = existing["id"]
    else:
        cur.execute(
            """INSERT INTO interview_prep (application_id, checklist_json, created_at, updated_at)
               VALUES (?, ?, ?, ?)""",
            (application_id, payload, now(), now()),
        )
        prep_id = cur.lastrowid
    conn.commit()
    conn.close()
    return prep_id, json.loads(payload)


def toggle_prep_item(prep_id: int, item_index: int, done: bool):
    conn = get_connection()
    row = conn.execute("SELECT checklist_json FROM interview_prep WHERE id = ?", (prep_id,)).fetchone()
    data = json.loads(row["checklist_json"])
    if 0 <= item_index < len(data["checklist"]):
        data["checklist"][item_index]["done"] = done
    conn.execute(
        "UPDATE interview_prep SET checklist_json = ?, updated_at = ? WHERE id = ?",
        (json.dumps(data), now(), prep_id),
    )
    conn.commit()
    conn.close()


def get_dashboard_stats():
    conn = get_connection()
    apps = conn.execute("SELECT status, COUNT(*) as c FROM applications GROUP BY status").fetchall()
    total_apps = conn.execute("SELECT COUNT(*) as c FROM applications").fetchone()["c"]
    this_week = conn.execute(
        """SELECT COUNT(*) as c FROM applications
           WHERE applied_at >= date('now', '-7 days')"""
    ).fetchone()["c"]
    pending_followups = conn.execute(
        """SELECT f.*, jd.company, jd.title FROM follow_ups f
           JOIN applications a ON a.id = f.application_id
           JOIN job_descriptions jd ON jd.id = a.job_description_id
           WHERE f.completed = 0 AND f.due_date <= date('now', '+7 days')
           ORDER BY f.due_date"""
    ).fetchall()
    networking_due = conn.execute(
        """SELECT * FROM networking_contacts
           WHERE next_follow_up IS NOT NULL AND next_follow_up <= date('now', '+7 days')
           ORDER BY next_follow_up"""
    ).fetchall()
    discovered_apply = conn.execute(
        "SELECT COUNT(*) as c FROM discovered_jobs WHERE recommendation = 'apply' AND status = 'new'"
    ).fetchone()["c"]
    interviews = conn.execute(
        "SELECT COUNT(*) as c FROM applications WHERE status = 'interview'"
    ).fetchone()["c"]
    conn.close()
    return {
        "status_counts": {r["status"]: r["c"] for r in apps},
        "total_apps": total_apps,
        "applied_this_week": this_week,
        "pending_followups": [dict(r) for r in pending_followups],
        "networking_due": [dict(r) for r in networking_due],
        "discovered_apply": discovered_apply,
        "interviews": interviews,
    }
