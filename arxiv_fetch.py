"""
arxiv_fetch.py — Fetch ArXiv papers based on repo keyword patterns.
Runs as job 1 of insight_pipeline.yml.
"""
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

from utils.db import get_client
from config import (
    ARXIV_MAX_RESULTS, ARXIV_QUERIES_MAX, ARXIV_DELAY,
    ARXIV_LINK_MIN, BASE_ARXIV_QUERIES,
)

ARXIV_NS  = "http://www.w3.org/2005/Atom"
ARXIV_API = "https://export.arxiv.org/api/query"


# ── Extract keywords from recent repo analyses ─────────────────────────────────

def get_search_keywords(db) -> list[str]:
    since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    resp  = (
        db.table("ai_repos")
        .select("analysis_result, category")
        .not_.is_("analysis_result", "null")
        .gte("created_at", since)
        .execute()
    )

    keywords: set[str] = set()
    for r in (resp.data or []):
        a = r.get("analysis_result") or {}
        if a.get("skipped"):
            continue
        for m in (a.get("xai_methods") or []):
            if m:
                keywords.add(m.strip())
        d = a.get("ai_domain", "")
        if d and d != "Other":
            keywords.add(d)
        for t in (a.get("tech_stack") or [])[:2]:
            if t:
                keywords.add(t.strip())

    return list(keywords)[:ARXIV_QUERIES_MAX] + BASE_ARXIV_QUERIES


# ── ArXiv API query ────────────────────────────────────────────────────────────

def _get(el, tag: str) -> str:
    child = el.find(f"{{{ARXIV_NS}}}{tag}")
    return child.text.strip() if child is not None and child.text else ""


def fetch_arxiv_papers(query: str) -> list[dict]:
    resp = requests.get(
        ARXIV_API,
        params={
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": ARXIV_MAX_RESULTS,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"  ⚠️  ArXiv error {resp.status_code}")
        return []

    root    = ET.fromstring(resp.content)
    papers  = []
    for entry in root.findall(f"{{{ARXIV_NS}}}entry"):
        arxiv_id  = _get(entry, "id").split("/abs/")[-1]
        authors   = [
            a.find(f"{{{ARXIV_NS}}}name").text.strip()
            for a in entry.findall(f"{{{ARXIV_NS}}}author")
            if a.find(f"{{{ARXIV_NS}}}name") is not None
        ][:5]
        papers.append({
            "arxiv_id":     arxiv_id,
            "title":        _get(entry, "title").replace("\n", " ").strip(),
            "abstract":     _get(entry, "summary").replace("\n", " ").strip()[:800],
            "authors":      authors,
            "published":    _get(entry, "published")[:10],
            "url":          f"https://arxiv.org/abs/{arxiv_id}",
            "keywords":     [query],
            "linked_repos": [],
        })
    return papers


# ── Link papers → repos ────────────────────────────────────────────────────────

def link_papers_to_repos(papers: list[dict], db) -> list[dict]:
    resp  = (
        db.table("ai_repos")
        .select("repo_name, repo_url, analysis_result")
        .not_.is_("analysis_result", "null")
        .execute()
    )
    repos = resp.data or []

    for paper in papers:
        linked  = []
        p_words = set((paper["title"] + " " + paper["abstract"]).lower().split())
        for repo in repos:
            a = repo.get("analysis_result") or {}
            if a.get("skipped"):
                continue
            r_text  = " ".join(filter(None, [
                " ".join(a.get("xai_methods") or []),
                " ".join(a.get("tech_stack") or []),
                repo.get("repo_name", ""),
            ])).lower()
            overlap = len(p_words & set(r_text.split()))
            if overlap >= ARXIV_LINK_MIN:
                linked.append(repo["repo_name"])
        paper["linked_repos"] = linked[:5]

    return papers


# ── Main ───────────────────────────────────────────────────────────────────────

def run() -> None:
    db = get_client()
    print("🔬 Fetching ArXiv papers…")

    keywords   = get_search_keywords(db)
    print(f"  Keywords: {keywords[:5]}…")

    all_papers: list[dict] = []
    seen:       set[str]   = set()

    for kw in keywords[:ARXIV_QUERIES_MAX]:
        print(f"  🔍 {kw}")
        for p in fetch_arxiv_papers(kw):
            if p["arxiv_id"] not in seen:
                seen.add(p["arxiv_id"])
                all_papers.append(p)
        time.sleep(ARXIV_DELAY)

    print(f"  📄 {len(all_papers)} unique papers")
    all_papers = link_papers_to_repos(all_papers, db)

    saved = 0
    for paper in all_papers:
        try:
            db.table("arxiv_papers").upsert(paper, on_conflict="arxiv_id").execute()
            saved += 1
        except Exception as e:
            print(f"  ⚠️  Error saving {paper['arxiv_id']}: {e}")

    print(f"🎉 Saved {saved} papers.")


if __name__ == "__main__":
    run()
