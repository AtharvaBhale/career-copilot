"""
scripts/seed_from_resume.py
Run once (and again whenever your resume changes substantially) to load
your career history into the memory layer as discrete, retrievable items.

Usage:
    cd app
    python ../scripts/seed_from_resume.py

This hardcodes Atharva's resume content as of the version provided.
Edit the lists below directly when your resume changes, or use the
Streamlit "Manage Memory" page once it's built to add/edit items without
touching code.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import db
import memory


WORK_EXPERIENCE_BULLETS = [
    {
        "content": "Engineering a centralized data architecture for the AthletiChem platform, integrating wearable device data streams into a scalable single source of truth for real-time analytics.",
        "source_label": "Community Dreams Foundation - Data Scientist",
        "tags": ["data engineering", "real-time analytics", "data architecture"],
    },
    {
        "content": "Establishing Standard Operating Procedures for data pipeline workflows to enforce data integrity and drive consistent team adoption across departments.",
        "source_label": "Community Dreams Foundation - Data Scientist",
        "tags": ["process", "data pipelines", "SOPs"],
    },
    {
        "content": "Designed a scalable RAG pipeline for intelligent document search; deployed Mistral-7B locally via llama-cpp for secure, cost-efficient AI operations without cloud dependency.",
        "source_label": "Extern - AI & Data Science Extern",
        "tags": ["RAG", "LLM", "local deployment", "Mistral"],
    },
    {
        "content": "Built FAISS vector search with Hugging Face embeddings and a Gradio interface to surface technical capabilities for non-technical stakeholders.",
        "source_label": "Extern - AI & Data Science Extern",
        "tags": ["FAISS", "vector search", "Hugging Face", "Gradio"],
    },
    {
        "content": "Developed and optimized data-driven features using Java, Spring Boot, and SQL for high-traffic applications serving 1M+ users; refactored SQL queries to cut execution time by 30%.",
        "source_label": "Tata Consultancy Services - System Engineer",
        "tags": ["Java", "Spring Boot", "SQL", "performance"],
    },
    {
        "content": "Managed IAM for European banking clients via IBM ISAM; built GCP-based CI/CD workflows and automated operational tasks via shell scripting, improving team turnaround by 20%.",
        "source_label": "Tata Consultancy Services - System Engineer",
        "tags": ["IAM", "IBM ISAM", "GCP", "CI/CD", "shell scripting"],
    },
    {
        "content": "Built RESTful APIs using Spring Boot and deployed via Google Apigee for enterprise clients; implemented SAML token-based authentication for a UK-based fintech payment platform.",
        "source_label": "NeosAlpha Technologies - Software Engineer",
        "tags": ["REST APIs", "Spring Boot", "Apigee", "SAML", "fintech"],
    },
    {
        "content": "Wrote unit/integration tests with Mocha & Chai, increasing code coverage by 35%; automated API lifecycle to reduce deployment cycles by 40% and test runtime by 85-90%.",
        "source_label": "NeosAlpha Technologies - Software Engineer",
        "tags": ["testing", "Mocha", "Chai", "CI/CD", "automation"],
    },
]

PROJECTS = [
    {
        "content": "Healthcare Assistant Chatbot: RAG + Google Gemini Streamlit app handling 500+ healthcare queries/day; 90% response accuracy with multi-version iterative development (v1-v8).",
        "source_label": "Project - Healthcare Assistant Chatbot",
        "tags": ["RAG", "Gemini", "Streamlit", "healthcare"],
    },
    {
        "content": "Capture - OCR Desktop Tool: Java + Tesseract OCR with multithreaded processing; automated 75% of manual data entry and reduced documentation time by 50%, handling 100+ extractions/day.",
        "source_label": "Project - Capture OCR Desktop Tool",
        "tags": ["Java", "Tesseract", "OCR", "multithreading"],
    },
    {
        "content": "PizzaSwing - Order Management System: Full-stack Java Swing desktop app with MySQL integration and JCalendar scheduling; end-to-end order lifecycle management with structured MVC architecture.",
        "source_label": "Project - PizzaSwing",
        "tags": ["Java Swing", "MySQL", "MVC", "desktop app"],
    },
    {
        "content": "Travelers UMC Subrogation Modeling: Classification model for insurance claims prioritization; recognized by judges for Model Transparency and Business Impact at a Hartford, CT competition.",
        "source_label": "Project - Travelers UMC Subrogation Modeling",
        "tags": ["classification", "insurance", "ML", "competition"],
    },
    {
        "content": "Weather App: Java-based application using OpenWeather API for real-time location-based forecasting with city search and optimized API call efficiency for smooth UX.",
        "source_label": "Project - Weather App",
        "tags": ["Java", "API integration", "OpenWeather"],
    },
]

SKILLS = [
    {"content": "Languages: Python, Java, SQL, R, JavaScript, C++", "tags": ["languages"]},
    {"content": "Frameworks & Libraries: Spring Boot, Pandas, NumPy, Scikit-learn, Matplotlib, Streamlit, Tesseract OCR, Apache Airflow", "tags": ["frameworks"]},
    {"content": "Tools & Platforms: GCP (Apigee), Docker, Kubernetes, Splunk, FAISS, Hugging Face, Firebase, Tableau, Git, Jira", "tags": ["tools"]},
    {"content": "Security & Identity: OAuth 2.0, SAML 2.0, JWT, IBM ISAM, REST APIs, RAG Pipelines", "tags": ["security", "identity"]},
]

CERTS = [
    {"content": "API Management with Google Apigee (Udemy)", "tags": ["certification", "Apigee"]},
    {"content": "Basics of Data Science (Cisco Networking Academy)", "tags": ["certification", "data science"]},
    {"content": "Linux Shell Scripting (LinkedIn Learning)", "tags": ["certification", "linux"]},
]

EDUCATION_AND_LEADERSHIP = [
    {"content": "MS in Data Science, University of Connecticut, Storrs, CT, Dec 2025. Coursework: ML, Data Engineering, Statistical Methods, NLP, Big Data Analytics.", "tags": ["education"]},
    {"content": "BTech in Electronics & Communication Engineering, Shri G.S. Institute of Technology & Science, Indore, India, Jun 2021.", "tags": ["education"]},
    {"content": "Lead Member, JonLof Leadership Academy (JLLA), UConn's premier leadership cohort, managing digital strategy and stakeholder engagement, Aug 2024 - Present.", "tags": ["leadership"]},
    {"content": "Finalist, Texas Instruments Innovation Challenge 2018. National Science Olympiad Chemistry AIR 211 (NSTSE). Robotics Club Event Coordinator & Project Mentor.", "tags": ["achievements"]},
]

CONTACT_AND_CONSTRAINTS = [
    {
        "content": "Based in Willimantic, CT. OPT EAD holder, STEM OPT eligible. Open to Software Engineer, Systems Engineer, Business Analyst, Technical PM, Project Coordinator, Data Analyst, and related early-career roles.",
        "tags": ["constraints", "work authorization", "target roles"],
    },
]


def run():
    db.init_db()
    count = 0

    for b in WORK_EXPERIENCE_BULLETS:
        memory.add_source_item("bullet", b["content"], b["source_label"], b["tags"])
        count += 1
    for p in PROJECTS:
        memory.add_source_item("project", p["content"], p["source_label"], p["tags"])
        count += 1
    for s in SKILLS:
        memory.add_source_item("skill", s["content"], None, s["tags"])
        count += 1
    for c in CERTS:
        memory.add_source_item("cert", c["content"], None, c["tags"])
        count += 1
    for e in EDUCATION_AND_LEADERSHIP:
        memory.add_source_item("summary", e["content"], None, e["tags"])
        count += 1
    for c in CONTACT_AND_CONSTRAINTS:
        memory.add_source_item("summary", c["content"], None, c["tags"])
        count += 1

    print(f"Seeded {count} source items into memory at {db.DB_PATH}")


if __name__ == "__main__":
    run()
