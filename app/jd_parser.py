"""
jd_parser.py
Turns raw job posting text (pasted by the user or sent by the browser
extension) into structured fields. One LLM call, JSON out.
"""

import json
from llm import _chat


def parse_jd(raw_text: str, url: str = None, source_platform: str = None):
    system_prompt = """Extract structured fields from a raw job posting.
Respond ONLY with valid JSON, no markdown fences, in this exact shape:
{
  "company": "string or null",
  "title": "string or null",
  "responsibilities": ["string", ...],
  "requirements": ["string", ...],
  "preferred_skills": ["string", ...]
}
If a field cannot be determined from the text, use null or an empty list.
Do not invent a company or title if it is not present in the text.
"""
    user_prompt = f"RAW JOB POSTING TEXT:\n{raw_text}\n\nReturn the JSON now."
    raw = _chat(system_prompt, user_prompt, temperature=0.0)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {
            "company": None,
            "title": None,
            "responsibilities": [],
            "requirements": [],
            "preferred_skills": [],
        }
    parsed["url"] = url
    parsed["source_platform"] = source_platform
    parsed["raw_text"] = raw_text
    return parsed
