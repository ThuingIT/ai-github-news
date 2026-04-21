"""
fetch_repos.py — Fetch GitHub repos and upsert into Supabase.
Runs as job 1 of daily_pipeline.yml.
"""
import os
import requests
from datetime import datetime, timedelta

from utils.db import get_client
from config import (
    FETCH_DAYS_WINDOW, XAI_MIN_STARS, TRENDING_MIN_STARS, GITHUB_QUERIES,
)

GITHUB_TOKEN = os.environ.get("GIT_TOKEN")
if not GITHUB_TOKEN:
    print("❌ GIT_TOKEN not set.")
    exit(1)

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

MIN_STARS = {"XAI": XAI_MIN_STARS, "Trending AI": TRENDING_MIN_STARS}


def build_query(topic: str, category: str, since: str) -> str:
    stars = MIN_STARS[category]
    return f"topic:{topic} created:>{since} stars:>{stars}"


def fetch_and_save() -> None:
    db    = get_client()
    since = (datetime.now() - timedelta(days=FETCH_DAYS_WINDOW)).strftime("%Y-%m-%d")

    for q in GITHUB_QUERIES:
        category = q["category"]
        topic    = q["topic"]
        print(f"\n▶ [{category}] topic:{topic}")

        resp = requests.get(
            "https://api.github.com/search/repositories",
            headers=HEADERS,
            params={"q": build_query(topic, category, since), "sort": "stars", "order": "desc"},
        )

        if resp.status_code != 200:
            print(f"  ✗ GitHub API error {resp.status_code}: {resp.text[:200]}")
            continue

        repos = resp.json().get("items", [])
        print(f"  → {len(repos)} repos found")

        for repo in repos:
            data = {
                "repo_name":   repo["full_name"],
                "repo_url":    repo["html_url"],
                "description": repo.get("description"),
                "stars":       repo["stargazers_count"],
                "topics":      repo.get("topics", []),
                "category":    category,
                "readme_url":  (
                    f"https://raw.githubusercontent.com/"
                    f"{repo['full_name']}/{repo['default_branch']}/README.md"
                ),
            }
            try:
                db.table("ai_repos").insert(data).execute()
                print(f"  + {repo['full_name']}")
            except Exception as e:
                msg = str(e)
                if "duplicate key" in msg or "23505" in msg:
                    print(f"  ~ already exists: {repo['full_name']}")
                else:
                    print(f"  ✗ DB error for {repo['full_name']}: {msg}")


if __name__ == "__main__":
    fetch_and_save()
