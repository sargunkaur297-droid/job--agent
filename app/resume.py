"""Resume loading and skill detection."""
from __future__ import annotations

import os
import re
from pathlib import Path

from .config import ROOT

SKILL_VOCAB = [
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust", "sql", "mysql", "postgresql",
    "mongodb", "excel", "power bi", "tableau", "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch",
    "machine learning", "deep learning", "nlp", "computer vision", "statistics", "data analysis",
    "data visualization", "etl", "spark", "hadoop", "airflow", "kafka", "aws", "azure", "gcp", "docker",
    "kubernetes", "git", "linux", "ci/cd", "jenkins", "terraform", "react", "angular", "node.js", "django",
    "flask", "fastapi", "spring boot", "html", "css", "rest api", "selenium", "pytest", "junit", "manual testing",
    "automation testing", "streamlit", "flutter", "android", "oop", "data structures", "algorithms",
    "web scraping", "llm", "generative ai", "looker", "dbt", "snowflake", "bigquery",
]


def load_resume_text(folder: Path | None = None) -> str:
    env = os.getenv("RESUME_TEXT")
    if env and env.strip():
        return env
    folder = folder or ROOT / "resume"
    chunks = []
    for f in sorted(folder.glob("*")) if folder.exists() else []:
        ext = f.suffix.lower()
        try:
            if ext == ".pdf":
                from pypdf import PdfReader
                chunks.append("\n".join(p.extract_text() or "" for p in PdfReader(str(f)).pages))
            elif ext == ".docx":
                import docx
                chunks.append("\n".join(p.text for p in docx.Document(str(f)).paragraphs))
            elif ext in (".txt", ".md"):
                chunks.append(f.read_text(encoding="utf-8", errors="ignore"))
        except Exception as e:  # corrupt file shouldn't kill the run
            print(f"[resume] could not read {f.name}: {e}")
    return "\n".join(chunks).strip()


def detect_skills(text: str, extra=()) -> list[str]:
    low = (text or "").lower()
    found = [s for s in SKILL_VOCAB
             if re.search(r"(?<![a-z0-9+#])%s(?![a-z0-9+#])" % re.escape(s), low)]
    for s in extra:
        if s.lower() not in found:
            found.append(s.lower())
    return found
