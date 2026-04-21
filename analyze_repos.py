"""
analyze_repos.py — Analyse un-analysed repos with Gemini.
Runs as job 2 of daily_pipeline.yml.
"""
import os
import json
import time
import requests

from google import genai
from google.genai import types

from utils.db import get_client
from config import (
    GEMINI_MODEL, PROMPTS, FILTER_KEYWORDS,
    README_MAX_CHARS, GEMINI_RETRIES, GEMINI_RETRY_DELAY,
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("❌ GEMINI_API_KEY not set.")
    exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)


# ── README extraction ──────────────────────────────────────────────────────────

PRIORITY_HEADERS = {
    "## method", "## approach", "## how", "## model", "## result",
    "## contribution", "## abstract", "## overview", "## innovation",
    "## feature", "## benchmark", "## architecture",
}


def extract_readme(text: str, max_chars: int = README_MAX_CHARS) -> str:
    lines, important, capture = text.split("\n"), [], False
    for line in lines:
        is_header    = line.strip().startswith("#")
        is_important = any(kw in line.lower() for kw in PRIORITY_HEADERS)
        if is_header:
            capture = is_important
        if capture:
            important.append(line)

    intro    = text[:300]
    combined = (intro + "\n\n" + "\n".join(important)).strip()
    result   = combined if len(combined) > 200 else text
    result   = result[:max_chars]
    print(f"  📝 README: {len(text)} → {len(result)} chars")
    return result


# ── Gemini call ────────────────────────────────────────────────────────────────

def call_gemini(prompt: str) -> dict | None:
    for attempt in range(1, GEMINI_RETRIES + 1):
        try:
            print(f"  🤖 Gemini call #{attempt}")
            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(max_output_tokens=2048),
            )
            text = resp.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            result = json.loads(text)
            print("  ✅ Parsed OK")
            return result
        except Exception as e:
            print(f"  ⚠️  Attempt {attempt}/{GEMINI_RETRIES}: {e}")
            time.sleep(GEMINI_RETRY_DELAY * attempt)
    return None


# ── Pre-filter ─────────────────────────────────────────────────────────────────

def is_likely_relevant(repo: dict) -> bool:
    category = repo.get("category", "")
    keywords = FILTER_KEYWORDS.get(category, [])
    text = " ".join(filter(None, [
        repo.get("description"),
        repo.get("repo_name"),
        " ".join(repo.get("topics") or []),
    ])).lower()
    matched = [kw for kw in keywords if kw in text]
    if matched:
        print(f"  ✓ Keywords: {matched[:3]}")
        return True
    print("  ⏭  No keyword match — skip")
    return False


# ── Main pipeline ──────────────────────────────────────────────────────────────

def analyze_repos() -> None:
    db    = get_client()
    repos = (
        db.table("ai_repos")
        .select("*")
        .is_("analysis_result", "null")
        .execute()
        .data
    )

    if not repos:
        print("✅ No repos need analysis.")
        return

    print(f"📦 {len(repos)} repos to analyse.\n")
    stats = {"done": 0, "skipped": 0, "error": 0}

    for repo in repos:
        category = repo.get("category", "Unknown")
        print(f"\n── [{category}] {repo['repo_name']} ──")

        def skip(reason: str):
            db.table("ai_repos").update({
                "analysis_result": {"skipped": True, "reason": reason, "category": category}
            }).eq("id", repo["id"]).execute()
            stats["skipped"] += 1

        # 1. Keyword pre-filter
        if not is_likely_relevant(repo):
            skip("no_keyword_match")
            continue

        # 2. Fetch README
        try:
            readme_resp = requests.get(repo["readme_url"], timeout=10)
        except requests.exceptions.Timeout:
            print("  ✗ README fetch timeout")
            stats["error"] += 1
            continue

        if readme_resp.status_code != 200:
            print(f"  ✗ README HTTP {readme_resp.status_code}")
            stats["error"] += 1
            continue

        # 3. Extract + prompt
        readme_summary = extract_readme(readme_resp.text)
        system_prompt  = PROMPTS.get(category, PROMPTS["Trending AI"])
        full_prompt    = system_prompt + "\n\nREADME:\n" + readme_summary
        print(f"  📨 Prompt length: {len(full_prompt)} chars")

        # 4. Call Gemini
        analysis = call_gemini(full_prompt)
        if analysis is None:
            print("  ✗ Gemini failed after all retries")
            stats["error"] += 1
            continue

        # 5. Skip surveys / awesome lists
        if analysis.get("is_survey_or_awesome_list"):
            print("  ⏭  Survey/awesome-list — skip")
            skip("survey_or_awesome_list")
            continue

        # 6. Attach metadata and save
        analysis["_meta"] = {
            "category":    category,
            "analyzed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "input_chars": len(full_prompt),
        }
        db.table("ai_repos").update({"analysis_result": analysis}).eq("id", repo["id"]).execute()
        print(f"  ✅ relevance_score: {analysis.get('relevance_score', '?')}/10")
        stats["done"] += 1

        time.sleep(1)

    print(f"\n{'='*40}")
    print(f"Done ✅ {stats['done']} | Skipped ⏭  {stats['skipped']} | Error ✗ {stats['error']}")


if __name__ == "__main__":
    analyze_repos()
