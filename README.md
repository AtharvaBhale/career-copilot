# Career Copilot

A personal job-search automation app for OPT/STEM OPT candidates. Discover fresh
openings, tailor ATS-optimized resumes and cover letters from your real career
history, find contacts, draft cold emails, and stay organized with trackers and
a weekly dashboard.

Built for deployment on **Streamlit Cloud + GitHub** using only **free tools**
([free-for.dev](https://free-for.dev/)).

## What it does

### 1. Discover fresh OPT-friendly jobs
- Pulls from free public APIs: **Remotive**, **Arbeitnow**, **RemoteOK**
- Optional **Adzuna** (free tier) for more US listings
- Filters common OPT blockers (`no sponsorship`, `US citizen only`, etc.)
- LLM scores match + interview likelihood and recommends **Apply / Maybe / Skip**
- Inspired by [Avisa](https://avisajob.com/)'s sponsor-aware job filtering

### 2. ATS-optimized resume tailoring
- Retrieves your real bullets/projects/skills via semantic search
- Transforms responsibilities into measurable achievements
- Strong action verbs, JD keyword alignment, 6-second recruiter scan layout
- Exactly **1 page or 2 pages** (never 1.5)
- Separate **truth-check** pass flags invented claims

### 3. Personalized cover letters
- Concise, JD-specific, uses only verified resume facts
- OPT/STEM OPT messaging when relevant

### 4. Outreach (Clearbit-style, free)
- Email pattern guessing + LinkedIn people search URLs
- Optional **Hunter.io** free tier (25 searches/month)
- Cold email drafts tied to your tailored resume

### 5. Stay organized
- Application status tracker
- Follow-up scheduler
- Networking contact tracker
- Interview prep checklist (LLM-generated)
- Weekly progress dashboard

### 6. Chrome extension (optional)
- Extract JDs from LinkedIn, Indeed, Handshake, Greenhouse, Lever, Ashby, Workday
- Sends to local API for review in Streamlit

## Project structure

```
career-copilot/
  app/
    app.py              Streamlit UI
    db.py               SQLite schema
    memory.py           Career memory + embeddings
    llm.py              Groq prompts (free tier)
    jd_parser.py        JD structuring
    pipeline.py         Generate + tracker orchestration
    job_discovery.py    Free job APIs + OPT filter
    outreach.py         Contact finding + cold email
    backup.py           GitHub DB backup for Streamlit Cloud
    extension_api.py    Browser extension receiver
  extension/            Chrome extension
  scripts/seed_from_resume.py
  requirements.txt
```

## Local setup

```bash
cd career-copilot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit secrets.toml — at minimum set GROQ_API_KEY (free at console.groq.com)

cd app
python ../scripts/seed_from_resume.py   # load your resume into memory
streamlit run app.py
```

Open http://localhost:8501

## Free tools used

| Tool | Purpose | Cost |
|------|---------|------|
| [Groq](https://console.groq.com) | LLM (resume, cover letter, scoring) | Free tier |
| [Remotive API](https://remotive.com/api/remote-jobs) | Remote jobs | Free, no key |
| [Arbeitnow API](https://arbeitnow.com/api/job-board-api) | Job board | Free, no key |
| [RemoteOK API](https://remoteok.com/api) | Remote jobs | Free, no key |
| [Adzuna API](https://developer.adzuna.com) | US jobs (optional) | Free tier |
| [Hunter.io](https://hunter.io) | Email discovery (optional) | 25 free/month |
| [Streamlit Cloud](https://streamlit.io/cloud) | Hosting | Free |
| [GitHub](https://github.com) | Code + private DB backup | Free |
| sentence-transformers | Local embeddings | Free, runs on CPU |

## Deploy to Streamlit Cloud

1. Push this repo to GitHub.
2. Create a **private** repo for SQLite backup (e.g. `career-copilot-data`).
3. On Streamlit Cloud, point the app at `app/app.py`.
4. Add secrets:
   ```
   GROQ_API_KEY = "..."
   GITHUB_TOKEN = "..."
   GITHUB_REPO = "yourusername/career-copilot-data"
   GITHUB_BRANCH = "main"
   ```
5. Seed memory via the Memory page or run `seed_from_resume.py` locally and backup.

## Chrome extension (optional)

```bash
# Terminal 2, from app/
export GROQ_API_KEY=...
export EXTENSION_API_TOKEN=your-random-token
uvicorn extension_api:api --host 0.0.0.0 --port 8765
```

Load `extension/` as unpacked in Chrome. Set API URL to `http://localhost:8765`.

## Typical workflow

1. **Dashboard** — check weekly goals and follow-ups
2. **Discover Jobs** — fetch today's OPT-friendly openings, import strong matches
3. **Generate** — tailor 1-page resume + cover letter, review truth-check
4. **Outreach** — find recruiter contacts, draft cold email
5. **Tracker** — mark applied, schedule follow-up, generate interview prep

## Your profile (pre-seeded)

The seed script loads Atharva Bhale's UConn MSDS resume: TCS, Extern, Community Dreams
Foundation, NeosAlpha experience, RAG/ML projects, OPT EAD + STEM OPT eligibility.

Edit `scripts/seed_from_resume.py` or use the **Memory** page when your resume changes.

## OPT messaging defaults

Load suggested preferences on the **Preferences** page:
- Currently authorized on F-1 OPT EAD
- STEM OPT eligible after Feb 2027
- Future H-1B needed for long-term stay (standard honest framing)

See [F1Jobs sponsorship guide](https://www.f1jobs.io/resources/blog/answer-do-you-need-sponsorship-interview) for interview scripts.

## Limitations

- Job APIs surface a subset of US roles (mostly remote/tech). Pair with LinkedIn/Handshake alerts and the browser extension for roles not in APIs.
- Contact finding uses heuristics, not paid databases like Clearbit. Verify emails before sending.
- LLM scoring is advisory; always read the JD yourself before applying.
