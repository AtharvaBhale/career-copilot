"""
extension_api.py
A tiny FastAPI app, separate process from Streamlit, whose only job is
to receive JD text from the browser extension and store it via the same
pipeline.ingest_job_description() the Streamlit UI uses.

Why a separate process: Streamlit apps don't expose a clean REST
endpoint for external callers (the extension), so this small API does
that one job. It shares the same SQLite file as app.py.

Run locally:
    cd app
    uvicorn extension_api:api --host 0.0.0.0 --port 8765

Deployment note: Streamlit Cloud only runs the Streamlit process, so
this API needs to run somewhere else if you want the extension to work
against your cloud deployment, for example a small always-on box (your
Pi works fine for this), or a free tier on Render/Fly.io. For local use
(testing the extension against your own machine) just run it locally
alongside `streamlit run app.py`.
"""

import os
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Optional

import pipeline

api = FastAPI(title="Career Copilot Extension Receiver")

# Simple shared-secret auth: the extension sends this header, since this
# is a single-user system, not a real auth system, this is sufficient to
# stop randoms on the internet from writing into your DB.
EXPECTED_TOKEN = os.environ.get("EXTENSION_API_TOKEN", "change-me")


class JDPayload(BaseModel):
    text: str
    url: Optional[str] = None
    platform: Optional[str] = None


def _check_auth(x_api_token: Optional[str]):
    if x_api_token != EXPECTED_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Token header.")


@api.post("/ingest_jd")
def ingest_jd(payload: JDPayload, x_api_token: Optional[str] = Header(None)):
    _check_auth(x_api_token)
    if not payload.text or len(payload.text.strip()) < 30:
        raise HTTPException(status_code=400, detail="JD text looks too short to be useful, did extraction work?")
    jd_id, parsed = pipeline.ingest_job_description(
        payload.text, url=payload.url, source_platform=payload.platform
    )
    return {"job_description_id": jd_id, "parsed": parsed}


@api.get("/health")
def health():
    return {"status": "ok"}
