"""
app.py
Career Copilot - single-user Streamlit app for OPT job search automation.

Pages:
- Dashboard: weekly progress, follow-ups, networking reminders
- Discover: fresh OPT-friendly jobs from free APIs
- Generate: tailor resume + cover letter for a JD
- Outreach: find contacts + cold email drafts
- Tracker: applications, follow-ups, interview prep
- History / Memory / Preferences
"""

import os
import json
from datetime import date, timedelta

import streamlit as st

import backup

DB_PATH = os.environ.get("CAREER_DB_PATH", "data/career.db")

for key in (
    "GROQ_API_KEY", "GITHUB_TOKEN", "GITHUB_REPO", "GITHUB_BRANCH",
    "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "HUNTER_API_KEY",
):
    if key in st.secrets and key not in os.environ:
        os.environ[key] = st.secrets[key]

if "db_restored" not in st.session_state:
    restored, msg = backup.restore_db(DB_PATH)
    st.session_state["db_restored"] = True
    st.session_state["restore_message"] = msg

import db
import memory
import pipeline
import job_discovery
import outreach
import profile

db.init_db()

GROQ_CONFIGURED = bool(os.environ.get("GROQ_API_KEY"))


def do_backup():
    ok, msg = backup.backup_db(DB_PATH)
    if not ok and "not configured" not in msg:
        st.warning(f"Backup issue: {msg}")


st.set_page_config(page_title="Career Copilot", page_icon="🎯", layout="wide")
st.title("Career Copilot")
st.caption("OPT job search automation · UConn MSDS · STEM OPT eligible Feb 2027")

if st.session_state.get("restore_message"):
    st.caption(st.session_state["restore_message"])

if not GROQ_CONFIGURED:
    st.error(
        "**GROQ_API_KEY is missing.** Resume, cover letter, and LLM job scoring will not work. "
        "Add it in Streamlit Cloud: **Manage app → Settings → Secrets**, then reboot the app."
    )

memory_count = len(memory.all_active_items())
if memory_count == 0:
    st.warning(
        "**Setup needed:** Your career memory is empty. Go to **Profile** to save your details, "
        "then **Memory** to add resume bullets (or run `seed_from_resume.py` locally once)."
    )

page = st.sidebar.radio(
    "Navigate",
    [
        "Dashboard",
        "Profile",
        "Discover Jobs",
        "Generate",
        "Outreach",
        "Tracker",
        "History",
        "Memory",
        "Preferences",
    ],
)

# -------------------------------------------------------------- Dashboard
if page == "Dashboard":
    st.header("Weekly progress dashboard")
    stats = pipeline.get_dashboard_stats()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total applications", stats["total_apps"])
    c2.metric("Applied this week", stats["applied_this_week"])
    c3.metric("Interviews", stats["interviews"])
    c4.metric("New 'Apply' jobs", stats["discovered_apply"])
    c5.metric("Follow-ups due (7d)", len(stats["pending_followups"]))

    st.subheader("Application pipeline")
    if stats["status_counts"]:
        st.bar_chart(stats["status_counts"])
    else:
        st.info("No applications yet. Discover jobs or generate a tailored resume to start.")

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Follow-ups due soon")
        if stats["pending_followups"]:
            for fu in stats["pending_followups"]:
                st.write(f"**{fu['company']}** · {fu['title']} · due {fu['due_date'][:10]} ({fu['follow_up_type']})")
                if st.button("Mark done", key=f"fu_done_{fu['id']}"):
                    pipeline.complete_follow_up(fu["id"])
                    do_backup()
                    st.rerun()
        else:
            st.success("No follow-ups due in the next 7 days.")

    with col_b:
        st.subheader("Networking follow-ups")
        if stats["networking_due"]:
            for nc in stats["networking_due"]:
                st.write(f"**{nc['name'] or 'Contact'}** @ {nc['company']} · due {nc['next_follow_up'][:10]}")
        else:
            st.success("No networking follow-ups due soon.")

    st.divider()
    st.subheader("This week's goals")
    g1, g2, g3 = st.columns(3)
    g1.metric("Target applications", "15/week", help="Adjust based on your capacity")
    g2.metric("Target outreach", "5/week", help="Cold emails or LinkedIn messages")
    g3.metric("Target networking", "3/week", help="Coffee chats, alumni calls")

# ------------------------------------------------------------------- Profile
elif page == "Profile":
    st.header("Your profile")
    st.caption(
        "Personalizes resumes, cover letters, outreach, and job scoring. "
        "This app is **single-user** today (one SQLite file). "
        "Multi-user support later needs login + separate data per user."
    )

    p = profile.get_profile()
    c1, c2 = st.columns(2)
    with c1:
        full_name = st.text_input("Full name", value=p.get("full_name") or "")
        first_name = st.text_input("First name", value=p.get("first_name") or "")
        last_name = st.text_input("Last name", value=p.get("last_name") or "")
        email = st.text_input("Email", value=p.get("email") or "")
    with c2:
        phone = st.text_input("Phone", value=p.get("phone") or "")
        location = st.text_input("Location", value=p.get("location") or "")
        linkedin = st.text_input("LinkedIn URL", value=p.get("linkedin_url") or "")

    target_roles = st.text_input(
        "Target roles (comma separated)",
        value=", ".join(p.get("target_roles") or []),
    )
    work_auth = st.text_area(
        "Work authorization summary (used in cover letters & outreach)",
        value=p.get("work_auth_summary") or "",
        height=100,
    )

    if st.button("Save profile", type="primary"):
        roles = [r.strip() for r in target_roles.split(",") if r.strip()]
        profile.save_profile(
            full_name, first_name, last_name, email, phone, location, linkedin, roles, work_auth
        )
        do_backup()
        st.success("Profile saved.")

    st.divider()
    st.subheader("Quick setup")
    st.markdown("""
1. **Save profile** above (name, OPT/STEM OPT wording, target roles).
2. Go to **Memory** and add resume bullets, projects, skills.
3. Go to **Preferences** and click **Load suggested OPT preferences**.
4. Optional: add `GROQ_API_KEY` in Streamlit Secrets for AI features.
    """)

# ----------------------------------------------------------- Discover Jobs
elif page == "Discover Jobs":
    st.header("Discover fresh OPT-friendly openings")
    st.caption(
        "Pulls from free APIs (Remotive, Arbeitnow, RemoteOK, optional Adzuna). "
        "Filters out common OPT blockers like 'no sponsorship' or 'US citizen only'. "
        "Inspired by [Avisa](https://avisajob.com/)'s sponsor-verified approach."
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        max_age = st.selectbox("Posted within", [1, 2, 3, 7], index=0, format_func=lambda d: f"{d} day(s)")
    with col2:
        use_llm = st.checkbox("LLM match scoring (uses Groq API)", value=True)
    with col3:
        rec_filter = st.selectbox("Show", ["all", "apply", "maybe", "skip"])

    if st.button("Fetch fresh jobs", type="primary"):
        with st.spinner("Fetching and scoring jobs..."):
            try:
                job_discovery.discover_jobs(max_age_days=max_age, score_with_llm=use_llm)
                do_backup()
                st.success("Job feed updated.")
            except Exception as exc:
                st.error(f"Job fetch failed: {exc}")

    jobs = job_discovery.list_discovered_jobs(
        recommendation=None if rec_filter == "all" else rec_filter,
    )

    if not jobs:
        st.info("No jobs found yet. Click 'Fetch fresh jobs' above.")
    else:
        st.write(f"**{len(jobs)}** job(s) in feed.")
        for job in jobs:
            rec = job.get("recommendation") or "maybe"
            badge = {"apply": "🟢 Apply", "maybe": "🟡 Maybe", "skip": "🔴 Skip"}.get(rec, rec)
            with st.expander(f"{badge} · {job['title']} at {job['company']} · match {job.get('match_score', 'n/a')}"):
                st.write(f"**Source:** {job['source']} · **Location:** {job['location']}")
                st.write(f"**Posted:** {job_discovery._posted_at_label(job.get('posted_at'))}")
                if job.get("url"):
                    st.markdown(f"[View posting]({job['url']})")
                st.write(job.get("recommendation_reason") or "")
                st.text(job["description"][:800] + ("..." if len(job["description"]) > 800 else ""))

                b1, b2, b3 = st.columns(3)
                if b1.button("Import & tailor", key=f"import_{job['id']}"):
                    jd_id, _ = job_discovery.import_to_jd(job["id"])
                    st.session_state["incoming_jd_id"] = jd_id
                    do_backup()
                    st.success(f"Imported as JD #{jd_id}. Go to **Generate** to tailor your resume.")
                if b2.button("Save for later", key=f"save_{job['id']}"):
                    job_discovery.update_discovered_status(job["id"], "saved")
                    do_backup()
                    st.rerun()
                if b3.button("Dismiss", key=f"dismiss_{job['id']}"):
                    job_discovery.update_discovered_status(job["id"], "dismissed")
                    do_backup()
                    st.rerun()

# ---------------------------------------------------------------- Generate
elif page == "Generate":
    st.header("Tailor resume + cover letter")

    incoming = st.session_state.pop("incoming_jd", None)
    incoming_jd_id = st.session_state.pop("incoming_jd_id", None)

    if incoming_jd_id:
        conn = db.get_connection()
        row = conn.execute("SELECT * FROM job_descriptions WHERE id = ?", (incoming_jd_id,)).fetchone()
        conn.close()
        if row:
            st.info(f"Loaded imported job: **{row['title']}** at **{row['company']}**")
            jd_text_default = row["raw_text"]
            url_default = row["url"] or ""
            platform_default = row["source_platform"] or ""
        else:
            jd_text_default = incoming.get("text", "") if incoming else ""
            url_default = incoming.get("url", "") if incoming else ""
            platform_default = ""
    else:
        jd_text_default = incoming.get("text", "") if incoming else ""
        url_default = incoming.get("url", "") if incoming else ""
        platform_default = ""

    jd_text = st.text_area("Paste the job description", value=jd_text_default, height=250)
    col1, col2 = st.columns(2)
    with col1:
        url = st.text_input("Job URL (optional)", value=url_default)
    with col2:
        platform = st.selectbox(
            "Platform",
            ["", "linkedin", "indeed", "handshake", "greenhouse", "lever", "ashby", "workday", "remotive", "other"],
            index=0,
        )

    max_pages = st.radio(
        "Resume length (must be exactly 1 or 2 pages, never 1.5)",
        [1, 2],
        horizontal=True,
    )

    if st.button("Generate tailored resume + cover letter", type="primary"):
        if not GROQ_CONFIGURED:
            st.error("Add GROQ_API_KEY in Streamlit Secrets first.")
        elif not jd_text.strip():
            st.error("Paste a job description first.")
        else:
            with st.spinner("Parsing job description..."):
                if incoming_jd_id:
                    jd_id = incoming_jd_id
                    parsed = {"title": row["title"], "company": row["company"]}
                else:
                    jd_id, parsed = pipeline.ingest_job_description(
                        jd_text, url=url or None, source_platform=platform or None
                    )
            st.success(f"Parsed: {parsed.get('title') or 'unknown title'} at {parsed.get('company') or 'unknown company'}")

            with st.spinner("Retrieving background, generating resume & cover letter..."):
                result = pipeline.generate_for_job(jd_id, max_pages=max_pages)
            do_backup()
            st.session_state["last_result"] = result
            st.session_state["last_jd_id"] = jd_id

    result = st.session_state.get("last_result")
    if result:
        st.divider()
        truth = result["truth_check"]
        ats = result["ats_score"]
        gap = result["skill_gap"]

        m1, m2, m3 = st.columns(3)
        m1.metric("ATS score", ats.get("score", "n/a"))
        m2.metric("Truth check", "Passed" if truth.get("passed") else "FLAGGED")
        m3.metric("Sources used", result["retrieved_count"])

        if ats.get("quick_wins"):
            st.info("ATS quick wins: " + " · ".join(ats["quick_wins"][:3]))

        if not truth.get("passed"):
            st.error("Unverified claims (review before sending):")
            for fc in truth.get("flagged_claims", []):
                st.write(f"- **{fc.get('claim')}**: {fc.get('reason')}")

        if gap.get("missing_skills"):
            st.warning("Skills in JD not in your background: " + ", ".join(gap["missing_skills"]))

        st.subheader("Tailored resume")
        edited_resume = st.text_area("Edit before saving", value=result["resume_markdown"], height=400, key="resume_edit")
        if st.button("Save resume edits"):
            pipeline.save_user_edit(resume_id=result["resume_id"], final_text=edited_resume)
            do_backup()
            st.success("Saved.")

        st.subheader("Cover letter")
        edited_cover = st.text_area("Edit before saving", value=result["cover_letter"], height=250, key="cover_edit")
        if st.button("Save cover letter edits"):
            pipeline.save_user_edit(cover_letter_id=result["cover_letter_id"], final_text=edited_cover)
            do_backup()
            st.success("Saved.")

        st.divider()
        st.subheader("Track this application")
        status = st.selectbox("Status", ["drafted", "applied", "referred", "interview", "rejected", "ghosted", "offer"])
        priority = st.selectbox("Priority", ["low", "medium", "high"])
        notes = st.text_input("Notes")
        if st.button("Update tracker"):
            app_id = pipeline.update_application_status(
                result["jd_id"], result["resume_id"], status, notes, priority
            )
            do_backup()
            st.success(f"Tracker updated (application #{app_id}).")

# ---------------------------------------------------------------- Outreach
elif page == "Outreach":
    st.header("Find contacts + draft cold email")
    st.caption(
        "Free contact discovery via email patterns and LinkedIn search. "
        "Optional Hunter.io (25 free searches/month) if HUNTER_API_KEY is set."
    )

    conn = db.get_connection()
    jds = conn.execute(
        "SELECT id, company, title FROM job_descriptions ORDER BY created_at DESC LIMIT 30"
    ).fetchall()
    conn.close()

    if not jds:
        st.info("Generate a tailored resume for a job first, or import one from Discover.")
    else:
        jd_options = {f"{r['title']} at {r['company']}": r["id"] for r in jds}
        selected = st.selectbox("Select job", list(jd_options.keys()))
        jd_id = jd_options[selected]

        conn = db.get_connection()
        jd_row = conn.execute("SELECT * FROM job_descriptions WHERE id = ?", (jd_id,)).fetchone()
        rv = conn.execute(
            "SELECT * FROM resume_versions WHERE job_description_id = ? ORDER BY created_at DESC LIMIT 1",
            (jd_id,),
        ).fetchone()
        conn.close()

        company = jd_row["company"] or "Unknown"
        user_p = profile.get_profile()
        contact_first = st.text_input("Contact first name (optional)", "")
        contact_last = st.text_input("Contact last name (optional)", "")

        if st.button("Find contacts"):
            result = outreach.find_contacts(
                company,
                jd_row["url"],
                your_first=user_p.get("first_name") or "",
                your_last=user_p.get("last_name") or "",
            )
            st.session_state["contacts_result"] = result

        contacts = st.session_state.get("contacts_result")
        if contacts:
            st.write(f"**Guessed domain:** {contacts.get('domain') or 'unknown'}")
            for i, c in enumerate(contacts["contacts"]):
                if c.get("linkedin_url"):
                    st.markdown(f"[LinkedIn people search]({c['linkedin_url']})")
                elif c.get("email"):
                    st.write(f"- {c.get('name') or 'Unknown'} · {c.get('title')} · `{c['email']}` ({c.get('source')})")

        resume_text = (rv["user_edited_final"] or rv["content_markdown"]) if rv else ""
        contact_name = f"{contact_first} {contact_last}".strip() or None
        contact_title = st.text_input("Contact title", "Recruiter")

        if st.button("Generate cold email", type="primary"):
            if not GROQ_CONFIGURED:
                st.error("Add GROQ_API_KEY in Streamlit Secrets first.")
            elif not resume_text:
                st.error("No resume found for this job. Generate one first.")
            else:
                with st.spinner("Drafting cold email..."):
                    prefs = memory.get_active_preferences()
                    email_draft = outreach.generate_cold_email(
                        jd_row["raw_text"], resume_text, contact_name, contact_title, prefs
                    )
                st.session_state["cold_email_draft"] = email_draft

        draft = st.session_state.get("cold_email_draft")
        if draft:
            edited = st.text_area("Cold email draft", value=draft, height=300)
            if st.button("Save outreach draft"):
                lines = edited.strip().split("\n", 1)
                subject = lines[0].replace("Subject:", "").strip() if lines else "Outreach"
                body = lines[1] if len(lines) > 1 else edited
                outreach.save_outreach(jd_id, subject, body, contact_name, None, contact_title)
                do_backup()
                st.success("Saved.")

# ----------------------------------------------------------------- Tracker
elif page == "Tracker":
    st.header("Application tracker")

    tab_apps, tab_follow, tab_net, tab_prep = st.tabs(
        ["Applications", "Follow-ups", "Networking", "Interview prep"]
    )

    with tab_apps:
        conn = db.get_connection()
        rows = conn.execute(
            """SELECT a.id, a.status, a.priority, a.notes, a.applied_at, a.updated_at,
                      jd.company, jd.title, jd.id as jd_id, rv.id as resume_id
               FROM applications a
               JOIN job_descriptions jd ON jd.id = a.job_description_id
               LEFT JOIN resume_versions rv ON rv.id = a.resume_version_id
               ORDER BY a.updated_at DESC"""
        ).fetchall()
        conn.close()

        if not rows:
            st.info("No applications yet.")
        else:
            st.dataframe(
                [{
                    "Company": r["company"],
                    "Title": r["title"],
                    "Status": r["status"],
                    "Priority": r["priority"],
                    "Applied": (r["applied_at"] or "")[:10],
                    "Updated": r["updated_at"][:10],
                    "Notes": r["notes"],
                } for r in rows],
                use_container_width=True,
            )

    with tab_follow:
        st.subheader("Schedule a follow-up")
        conn = db.get_connection()
        apps = conn.execute(
            """SELECT a.id, jd.company, jd.title FROM applications a
               JOIN job_descriptions jd ON jd.id = a.job_description_id
               ORDER BY a.updated_at DESC"""
        ).fetchall()
        conn.close()

        if apps:
            app_map = {f"{a['company']} - {a['title']}": a["id"] for a in apps}
            sel = st.selectbox("Application", list(app_map.keys()))
            due = st.date_input("Due date", value=date.today() + timedelta(days=7))
            ftype = st.selectbox("Type", ["email", "linkedin", "phone", "other"])
            fnote = st.text_input("Notes")
            if st.button("Schedule follow-up"):
                pipeline.schedule_follow_up(app_map[sel], due.isoformat(), ftype, fnote)
                do_backup()
                st.success("Follow-up scheduled.")

        conn = db.get_connection()
        all_fu = conn.execute(
            """SELECT f.*, jd.company, jd.title FROM follow_ups f
               JOIN applications a ON a.id = f.application_id
               JOIN job_descriptions jd ON jd.id = a.job_description_id
               ORDER BY f.due_date"""
        ).fetchall()
        conn.close()

        st.subheader("All follow-ups")
        for fu in all_fu:
            done = "✅" if fu["completed"] else "⏳"
            st.write(f"{done} **{fu['company']}** · due {fu['due_date'][:10]} · {fu['follow_up_type']}")
            if not fu["completed"] and st.button("Complete", key=f"complete_fu_{fu['id']}"):
                pipeline.complete_follow_up(fu["id"])
                do_backup()
                st.rerun()

    with tab_net:
        st.subheader("Add networking contact")
        n_name = st.text_input("Name")
        n_company = st.text_input("Company")
        n_title = st.text_input("Title")
        n_email = st.text_input("Email")
        n_linkedin = st.text_input("LinkedIn URL")
        n_rel = st.selectbox("Relationship", ["recruiter", "hiring_manager", "alumni", "referral", "other"])
        n_notes = st.text_area("Notes")
        set_next = st.checkbox("Set a follow-up reminder")
        n_next = st.date_input("Next follow-up", value=date.today() + timedelta(days=14), key="net_next", disabled=not set_next)

        if st.button("Add contact"):
            if n_name and n_company:
                pipeline.add_networking_contact(
                    n_name, n_company, n_title, n_email, n_linkedin, n_rel, n_notes,
                    next_follow_up=n_next.isoformat() if set_next else None,
                )
                do_backup()
                st.success("Contact added.")
            else:
                st.error("Name and company required.")

        conn = db.get_connection()
        contacts = conn.execute(
            "SELECT * FROM networking_contacts ORDER BY updated_at DESC"
        ).fetchall()
        conn.close()

        st.subheader("Your network")
        for c in contacts:
            st.write(f"**{c['name']}** · {c['title']} @ {c['company']} · {c['relationship']}")
            if c["email"]:
                st.caption(c["email"])
            if c["notes"]:
                st.caption(c["notes"])

    with tab_prep:
        st.subheader("Interview preparation checklist")
        conn = db.get_connection()
        prep_apps = conn.execute(
            """SELECT a.id, jd.company, jd.title, jd.raw_text, rv.content_markdown, rv.user_edited_final
               FROM applications a
               JOIN job_descriptions jd ON jd.id = a.job_description_id
               LEFT JOIN resume_versions rv ON rv.id = a.resume_version_id
               WHERE a.status IN ('interview', 'applied', 'referred')
               ORDER BY a.updated_at DESC"""
        ).fetchall()
        conn.close()

        if not prep_apps:
            st.info("Mark an application as 'interview' or 'applied' to generate prep.")
        else:
            prep_map = {f"{p['company']} - {p['title']}": p for p in prep_apps}
            sel_prep = st.selectbox("Application", list(prep_map.keys()))
            p = prep_map[sel_prep]
            resume = p["user_edited_final"] or p["content_markdown"] or ""

            if st.button("Generate interview prep", type="primary"):
                with st.spinner("Building checklist..."):
                    prep_id, data = pipeline.create_interview_prep(p["id"], p["raw_text"], resume)
                    st.session_state["prep_data"] = data
                    st.session_state["prep_id"] = prep_id
                do_backup()

            conn = db.get_connection()
            existing = conn.execute(
                "SELECT * FROM interview_prep WHERE application_id = ?", (p["id"],)
            ).fetchone()
            conn.close()

            if existing:
                data = json.loads(existing["checklist_json"])
                st.session_state["prep_id"] = existing["id"]

                st.markdown("**Checklist**")
                for i, item in enumerate(data.get("checklist", [])):
                    checked = st.checkbox(item["item"], value=item.get("done", False), key=f"prep_{existing['id']}_{i}")
                    if checked != item.get("done", False):
                        pipeline.toggle_prep_item(existing["id"], i, checked)
                        do_backup()

                if data.get("likely_questions"):
                    st.markdown("**Likely questions**")
                    for q in data["likely_questions"]:
                        st.write(f"- {q}")

                if data.get("stories_to_prepare"):
                    st.markdown("**STAR stories to prepare**")
                    for s in data["stories_to_prepare"]:
                        st.write(f"- {s}")

                if data.get("company_research"):
                    st.markdown("**Company research**")
                    for r in data["company_research"]:
                        st.write(f"- {r}")

# ----------------------------------------------------------------- History
elif page == "History":
    st.header("Past generations")
    conn = db.get_connection()
    rows = conn.execute(
        """SELECT rv.id as resume_id, jd.company, jd.title, jd.created_at, rv.ats_score,
                  rv.truth_check_passed, cl.id as cover_letter_id
           FROM resume_versions rv
           JOIN job_descriptions jd ON jd.id = rv.job_description_id
           LEFT JOIN cover_letters cl ON cl.resume_version_id = rv.id
           ORDER BY rv.created_at DESC"""
    ).fetchall()
    conn.close()

    if not rows:
        st.info("Nothing generated yet.")
    for r in rows:
        with st.expander(f"{r['title'] or 'Untitled'} at {r['company'] or 'Unknown'} — {r['created_at'][:10]}"):
            st.write(f"ATS score: {r['ats_score']} | Truth check passed: {bool(r['truth_check_passed'])}")
            conn = db.get_connection()
            rv = conn.execute("SELECT * FROM resume_versions WHERE id = ?", (r["resume_id"],)).fetchone()
            cl = None
            if r["cover_letter_id"]:
                cl = conn.execute("SELECT * FROM cover_letters WHERE id = ?", (r["cover_letter_id"],)).fetchone()
            conn.close()
            st.markdown(rv["user_edited_final"] or rv["content_markdown"])
            if cl:
                st.markdown("**Cover letter:**")
                st.markdown(cl["user_edited_final"] or cl["content"])

# ------------------------------------------------------------------ Memory
elif page == "Memory":
    st.header("Career memory")
    st.caption("Single source of truth for resume generation. Only verified facts here.")

    item_type_filter = st.selectbox("Filter by type", ["all", "bullet", "project", "skill", "cert", "summary"])
    items = memory.all_active_items(None if item_type_filter == "all" else item_type_filter)

    st.write(f"{len(items)} active item(s).")
    for item in items:
        cols = st.columns([5, 1])
        with cols[0]:
            label = f" ({item['source_label']})" if item["source_label"] else ""
            st.markdown(f"**[{item['item_type']}]**{label}: {item['content']}")
        with cols[1]:
            if st.button("Remove", key=f"remove_{item['id']}"):
                memory.deactivate_item(item["id"])
                do_backup()
                st.rerun()

    st.divider()
    st.subheader("Add a new memory item")
    new_type = st.selectbox("Type", ["bullet", "project", "skill", "cert", "summary"], key="new_item_type")
    new_label = st.text_input("Source label (optional)", key="new_item_label")
    new_content = st.text_area("Content", key="new_item_content")
    new_tags = st.text_input("Tags (comma separated)", key="new_item_tags")
    if st.button("Add to memory"):
        if new_content.strip():
            tags = [t.strip() for t in new_tags.split(",") if t.strip()]
            memory.add_source_item(new_type, new_content.strip(), new_label.strip() or None, tags)
            do_backup()
            st.success("Added.")
            st.rerun()
        else:
            st.error("Content can't be empty.")

# -------------------------------------------------------------- Preferences
elif page == "Preferences":
    st.header("Writing preferences + OPT messaging")
    st.caption(
        "Default suggestions are pre-loaded below. Add your own rules for tone, "
        "work authorization wording, and target roles."
    )

    default_prefs = [
        "Currently authorized on F-1 OPT EAD. STEM OPT eligible after Feb 2027.",
        "If sponsorship comes up: authorized now; will need H-1B for long-term employment.",
        "Target roles: Data Scientist, Software Engineer, Data Analyst, Systems Engineer, Business Analyst.",
        "Location: open to remote and USA-wide; based in Willimantic, CT.",
    ]

    prefs = memory.get_active_preferences()
    if not prefs:
        st.info("No preferences saved yet. Add the defaults or your own:")
        if st.button("Load suggested OPT preferences"):
            for p in default_prefs:
                memory.add_writing_preference(p)
            do_backup()
            st.rerun()

    for p in prefs:
        st.write(f"- {p}")

    new_pref = st.text_input("Add a preference")
    if st.button("Add preference"):
        if new_pref.strip():
            memory.add_writing_preference(new_pref.strip())
            do_backup()
            st.success("Added.")
            st.rerun()

    st.divider()
    st.subheader("Free API keys (optional)")
    st.markdown("""
- **Groq** (required): [console.groq.com](https://console.groq.com) — free LLM tier
- **Adzuna** (optional): [developer.adzuna.com](https://developer.adzuna.com) — more US job listings
- **Hunter.io** (optional): [hunter.io](https://hunter.io) — 25 free email searches/month
- **GitHub** (optional): private repo backup for Streamlit Cloud deploy
    """)
