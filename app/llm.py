"""
llm.py
Thin wrapper around the Groq API. Keeps all prompts in one place so
the writing-style constraints (no buzzwords, no em dashes, no fake
experience) are enforced consistently everywhere, not duplicated.

Groq free tier: https://console.groq.com (listed on free-for.dev)
"""

import os
import json
from groq import Groq

MODEL = "llama-3.3-70b-versatile"

_client = None


def client():
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY not set. Add it to your environment or "
                ".streamlit/secrets.toml as GROQ_API_KEY."
            )
        _client = Groq(api_key=api_key)
    return _client


STYLE_RULES = """
Writing rules, follow strictly:
- No em dashes, anywhere. Use periods or commas instead.
- No AI-sounding buzzwords: avoid "leverage", "synergy", "spearheaded",
  "passionate", "dynamic", "results-driven", "cutting-edge", "utilize".
  Use plain, specific verbs instead.
- No exaggerated claims and no invented experience. Every claim must be
  traceable to the source material provided. If the source material does
  not support a strong claim, write the honest, smaller claim instead.
- No keyword stuffing. Mention a skill only where it is true and relevant.
- Sound like a specific person wrote it, not a template.
"""

OPT_CONTEXT = """
Candidate work authorization context (use in cover letters / outreach only when relevant):
- F-1 OPT EAD holder, authorized to work in the U.S. now.
- STEM OPT eligible after Feb 2027 (MS Data Science, UConn).
- Will need H-1B sponsorship for long-term employment; no employer cost for OPT today.
- When asked about sponsorship: currently authorized; future H-1B needed.
"""


def _chat(system_prompt: str, user_prompt: str, temperature: float = 0.4):
    resp = client().chat.completions.create(
        model=MODEL,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return resp.choices[0].message.content


def _parse_json(raw: str, fallback: dict):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def generate_resume(jd_text: str, retrieved_items: list, preferences: list, max_pages: int = 1):
    source_block = "\n".join(
        f"- [{i['item_type']}] ({i.get('source_label') or 'unlabeled'}): {i['content']}"
        for i in retrieved_items
    )
    pref_block = "\n".join(f"- {p}" for p in preferences) or "(none set yet)"

    page_rule = (
        "Exactly 1 page of content when printed (roughly 450-550 words max)."
        if max_pages == 1
        else "Exactly 2 full pages of content when printed (roughly 900-1100 words). "
             "Do NOT produce 1.5 pages. Fill page 2 completely or trim to 1 page."
    )

    system_prompt = f"""You are an expert resume writer for early-career data/software roles.
{STYLE_RULES}

Resume optimization rules:
- Transform weak responsibilities into measurable achievements with numbers where the source supports them.
- Lead with the most JD-relevant experience and projects.
- Use strong action verbs: Built, Designed, Optimized, Engineered, Automated, Deployed.
- Standard ATS sections only: Summary, Skills, Experience, Projects, Education, Certifications.
- No tables, columns, graphics, or headers/footers. Plain markdown bullets.
- Recruiter scan test: top third must show role fit in under 6 seconds.
- Mirror JD keywords naturally where they match real skills (no stuffing).
- {page_rule}
You may ONLY use facts from the SOURCE MATERIAL below.
"""

    user_prompt = f"""JOB DESCRIPTION:
{jd_text}

SOURCE MATERIAL (the only facts you may draw from):
{source_block}

USER PREFERENCES:
{pref_block}

Write the tailored resume now, in markdown, with clear section headers.
"""
    return _chat(system_prompt, user_prompt)


def generate_cover_letter(jd_text: str, resume_markdown: str, preferences: list, tone_sample: str = None):
    pref_block = "\n".join(f"- {p}" for p in preferences) or "(none set yet)"
    tone_block = (
        f"\nHere is a sample of the user's own past writing, match this voice:\n{tone_sample}\n"
        if tone_sample else ""
    )

    system_prompt = f"""You write concise, personalized cover letters for job applications.
{STYLE_RULES}
{OPT_CONTEXT}

Rules:
- Under 280 words. Three short paragraphs max.
- Open with why this specific role/company (one concrete detail from the JD).
- Middle: 2-3 true achievements from the resume tied to JD requirements.
- Close: availability and brief work-auth clarity only if JD mentions authorization.
- No generic "I am excited to apply" openings.
"""

    user_prompt = f"""JOB DESCRIPTION:
{jd_text}

CANDIDATE'S TAILORED RESUME (only true facts, use only these):
{resume_markdown}

USER PREFERENCES:
{pref_block}
{tone_block}
Write the cover letter now.
"""
    return _chat(system_prompt, user_prompt)


def generate_cold_email(jd_text: str, resume_markdown: str, contact_name: str = None, contact_title: str = None, preferences: list = None):
    pref_block = "\n".join(f"- {p}" for p in preferences) or "(none set yet)"
    greeting = f"Address {contact_name}" if contact_name else "Use a professional generic greeting"

    system_prompt = f"""You write short cold outreach emails to recruiters or hiring managers.
{STYLE_RULES}
{OPT_CONTEXT}

Rules:
- Subject line on first line as "Subject: ..."
- Body under 150 words.
- One specific reason you fit this role (from resume, not invented).
- One ask: 15-minute chat or referral to hiring team.
- Professional, not salesy. No "I hope this email finds you well".
"""

    user_prompt = f"""JOB DESCRIPTION:
{jd_text[:3000]}

RESUME (true facts only):
{resume_markdown[:2500]}

CONTACT: {contact_name or 'unknown'} ({contact_title or 'recruiter/hiring manager'})
{greeting}

USER PREFERENCES:
{pref_block}

Write subject + email body now.
"""
    return _chat(system_prompt, user_prompt, temperature=0.5)


def score_job_match(jd_text: str, profile_summary: str):
    system_prompt = """You evaluate job fit for an OPT-eligible MS Data Science grad targeting
data scientist, software engineer, data analyst, and related early-career roles.

Respond ONLY with valid JSON:
{
  "match_score": 0-100,
  "interview_likelihood": 0-100,
  "recommendation": "apply" | "maybe" | "skip",
  "recommendation_reason": "2-3 sentences explaining why"
}

Scoring guide:
- match_score: skills/experience overlap with JD.
- interview_likelihood: realistic chance given seniority fit, OPT timing, and role level.
- "apply" if match_score >= 70 and interview_likelihood >= 50.
- "maybe" if partial fit or stretch role.
- "skip" if clear mismatch, too senior, or OPT blockers implied.
"""
    user_prompt = f"""CANDIDATE PROFILE:
{profile_summary}

JOB:
{jd_text[:5000]}

Return JSON now.
"""
    raw = _chat(system_prompt, user_prompt, temperature=0.0)
    return _parse_json(raw, {
        "match_score": 50,
        "interview_likelihood": 40,
        "recommendation": "maybe",
        "recommendation_reason": "Could not parse LLM response.",
    })


def generate_interview_prep(jd_text: str, resume_markdown: str):
    system_prompt = """Create an interview prep checklist for this candidate and role.
Respond ONLY with valid JSON:
{
  "checklist": [
    {"category": "Technical", "item": "...", "priority": "high|medium|low"},
    ...
  ],
  "likely_questions": ["...", "..."],
  "stories_to_prepare": ["STAR story about ...", ...],
  "company_research": ["...", ...]
}
Include 8-12 checklist items covering: JD skills, projects to discuss, behavioral STAR stories,
OPT/sponsorship talking points if relevant, and company research tasks.
"""
    user_prompt = f"""JOB DESCRIPTION:
{jd_text[:4000]}

RESUME:
{resume_markdown[:3000]}

Return JSON now.
"""
    raw = _chat(system_prompt, user_prompt, temperature=0.3)
    return _parse_json(raw, {"checklist": [], "likely_questions": [], "stories_to_prepare": [], "company_research": []})


def truth_check(resume_markdown: str, retrieved_items: list):
    source_block = "\n".join(f"- {i['content']}" for i in retrieved_items)

    system_prompt = """You are a strict fact-checker. You compare a resume
against a list of source facts. For every concrete claim in the resume
(numbers, technologies, job titles, achievements), determine if it is
directly supported by the source facts, a reasonable rephrasing of them,
or an unsupported addition.
Respond ONLY with valid JSON, no markdown fences, no preamble, in this
exact shape:
{"passed": true/false, "flagged_claims": [{"claim": "...", "reason": "..."}]}
"passed" is true only if flagged_claims is empty.
"""
    user_prompt = f"""SOURCE FACTS:
{source_block}

RESUME TO CHECK:
{resume_markdown}

Return the JSON now.
"""
    raw = _chat(system_prompt, user_prompt, temperature=0.0)
    return _parse_json(raw, {"passed": False, "flagged_claims": [{"claim": "PARSE_ERROR", "reason": raw[:500]}]})


def skill_gap_analysis(jd_text: str, retrieved_items: list):
    source_block = "\n".join(f"- {i['content']}" for i in retrieved_items)
    system_prompt = """Compare a job description's requirements against a
candidate's actual background. Respond ONLY with valid JSON, no markdown
fences, in this shape:
{"matched_skills": ["..."], "missing_skills": ["..."], "notes": "one or two honest sentences"}
"""
    user_prompt = f"""JOB DESCRIPTION:
{jd_text}

CANDIDATE BACKGROUND:
{source_block}

Return the JSON now.
"""
    raw = _chat(system_prompt, user_prompt, temperature=0.0)
    return _parse_json(raw, {"matched_skills": [], "missing_skills": [], "notes": raw[:500]})


def ats_score(jd_text: str, resume_markdown: str):
    system_prompt = """You score how well a resume's wording and structure
will parse and match in a typical ATS (applicant tracking system) for a
given job description. Respond ONLY with valid JSON:
{"score": 0-100, "reasons": ["..."], "quick_wins": ["..."]}
Score based on: keyword overlap with the JD, standard section headers,
no graphics/tables that break parsing, reverse-chronological clarity,
measurable bullets, and recruiter 6-second scan readability.
"""
    user_prompt = f"""JOB DESCRIPTION:
{jd_text}

RESUME:
{resume_markdown}

Return the JSON now.
"""
    raw = _chat(system_prompt, user_prompt, temperature=0.0)
    return _parse_json(raw, {"score": None, "reasons": [raw[:500]], "quick_wins": []})
