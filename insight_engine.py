"""
insight_engine.py — Personalized repo recommendations based on user preferences.
Runs as job 2 of insight_pipeline.yml.
"""
import os
import json
from datetime import datetime, timezone, timedelta

from groq import Groq

from utils.db import get_client
from utils.scoring import composite_score
from config import (
    GROQ_MODEL, GROQ_TEMPERATURE, GROQ_MAX_TOKENS,
    WEEKLY_DAYS, INSIGHT_TOP_REPOS,
)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("❌ GROQ_API_KEY not set.")
    exit(1)

groq_client = Groq(api_key=GROQ_API_KEY)


# ── Read user preferences ──────────────────────────────────────────────────────

def get_preferences(db) -> tuple[list, list]:
    def enrich(prefs: list) -> list:
        for p in prefs:
            rows = (
                db.table("ai_repos")
                .select("analysis_result, stars, category")
                .eq("repo_name", p["repo_name"])
                .limit(1)
                .execute()
                .data or []
            )
            p["ai_repo"] = rows[0] if rows else {}
        return prefs

    liked    = db.table("repo_preferences").select("*").eq("liked", True).execute().data or []
    disliked = db.table("repo_preferences").select("*").eq("liked", False).execute().data or []
    return enrich(liked), enrich(disliked)


# ── Analyse preference pattern via Groq ───────────────────────────────────────

def analyze_pattern(liked: list, disliked: list) -> dict | None:
    if not liked and not disliked:
        return None

    def fmt(prefs: list) -> str:
        lines = []
        for p in prefs[:10]:
            a = (p.get("ai_repo") or {}).get("analysis_result") or {}
            lines.append(
                f"- {p['repo_name']} | "
                f"domain: {a.get('ai_domain', '')} | "
                f"methods: {a.get('xai_methods', [])} | "
                f"cat: {(p.get('ai_repo') or {}).get('category', '')}"
            )
        return "\n".join(lines) if lines else "Chưa có"

    resp = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Bạn là chuyên gia phân tích preference AI. Trả về JSON thuần túy, không markdown.",
            },
            {
                "role": "user",
                "content": (
                    f"User liked:\n{fmt(liked)}\n\nUser disliked:\n{fmt(disliked)}\n\n"
                    'Return JSON: {"preferred_domains":[],"preferred_methods":[],'
                    '"preferred_categories":[],"avoid_domains":[],'
                    '"avoid_categories":[],"summary":"1-2 câu mô tả user quan tâm gì"}'
                ),
            },
        ],
        temperature=0.3,
        max_tokens=512,
    )
    text = resp.choices[0].message.content.strip()
    try:
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception:
        return {"summary": text}


# ── Score repos by preference ──────────────────────────────────────────────────

def score_by_preference(repos: list, pattern: dict | None) -> list:
    if not pattern:
        for r in repos:
            a         = r.get("analysis_result") or {}
            r["_score"] = composite_score(r.get("stars", 0) or 0, a.get("relevance_score", 0) or 0)
        return sorted(repos, key=lambda r: r["_score"], reverse=True)

    pref_domains  = [d.lower() for d in pattern.get("preferred_domains", [])]
    pref_methods  = [m.lower() for m in pattern.get("preferred_methods", [])]
    pref_cats     = [c.lower() for c in pattern.get("preferred_categories", [])]
    avoid_domains = [d.lower() for d in pattern.get("avoid_domains", [])]
    avoid_cats    = [c.lower() for c in pattern.get("avoid_categories", [])]

    for r in repos:
        a       = r.get("analysis_result") or {}
        domain  = (a.get("ai_domain") or "").lower()
        cat     = (r.get("category") or "").lower()
        methods = [m.lower() for m in (a.get("xai_methods") or [])]

        bonus = 0
        if domain in pref_domains:                  bonus += 30
        if cat    in pref_cats:                     bonus += 20
        bonus += sum(15 for m in methods if m in pref_methods)
        if domain in avoid_domains:                 bonus -= 40
        if cat    in avoid_cats:                    bonus -= 30

        base           = composite_score(r.get("stars", 0) or 0, a.get("relevance_score", 0) or 0)
        r["_score"]    = round(base + bonus, 1)

    return sorted(repos, key=lambda r: r["_score"], reverse=True)


# ── Write personalized briefing ────────────────────────────────────────────────

def write_briefing(top_repos: list, papers: list, pattern: dict | None, week_label: str) -> str:
    def fmt_repos(repos: list) -> str:
        return "\n".join(
            f"- {r['repo_name'].split('/')[-1]} "
            f"(score {r.get('_score', 0)}, {r.get('category', '')}, "
            f"problem: {(r.get('analysis_result') or {}).get('core_problem', '')[:60]})"
            for r in repos[:5]
        )

    def fmt_papers(papers: list) -> str:
        return "\n".join(
            f"- [{p['title'][:60]}]({p['url']}) ({p['published']}) "
            f"| Linked: {', '.join(p.get('linked_repos', [])[:2]) or 'none'}"
            for p in papers[:5]
        )

    pref_ctx = (
        f"User quan tâm: {pattern.get('summary', '')}\n"
        f"Domain ưa thích: {pattern.get('preferred_domains', '')}\n"
        f"Methods ưa thích: {pattern.get('preferred_methods', '')}"
        if pattern
        else "Chưa có preference."
    )

    resp = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Bạn là personal AI research assistant. Viết tiếng Việt, "
                    "tông cá nhân hoá — như viết riêng cho 1 người. Sâu sắc, có chính kiến."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Tuần {week_label} — Personal briefing\n\n"
                    f"Profile:\n{pref_ctx}\n\n"
                    f"Top repos phù hợp:\n{fmt_repos(top_repos)}\n\n"
                    f"Papers ArXiv:\n{fmt_papers(papers)}\n\n"
                    "Viết theo cấu trúc:\n\n"
                    "## 👤 Dành riêng cho bạn\n(Tại sao repos này phù hợp — cụ thể)\n\n"
                    "## 🔬 Từ lab đến code\n(Paper nào đang được implement? Gap nào?)\n\n"
                    "## ⚡ Xem ngay\n(1-2 repo, giải thích tại sao phù hợp)\n\n"
                    "## 🧭 Gợi ý mở rộng\n(Hướng nào nên khám phá tiếp?)"
                ),
            },
        ],
        temperature=GROQ_TEMPERATURE,
        max_tokens=GROQ_MAX_TOKENS,
    )
    return resp.choices[0].message.content


# ── Main ───────────────────────────────────────────────────────────────────────

def run() -> None:
    db         = get_client()
    week_label = datetime.now(timezone.utc).strftime("%Y-W%W")
    print(f"🧠 Insight Engine — {week_label}")

    liked, disliked = get_preferences(db)
    print(f"  👍 {len(liked)} liked | 👎 {len(disliked)} disliked")

    pattern = None
    if liked or disliked:
        print("  🤖 Analysing preference pattern…")
        pattern = analyze_pattern(liked, disliked)
        print(f"  → {(pattern or {}).get('summary', '')[:60]}")

    since = (datetime.now(timezone.utc) - timedelta(days=WEEKLY_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    repos = [
        r for r in (
            db.table("ai_repos")
            .select("*")
            .not_.is_("analysis_result", "null")
            .gte("created_at", since)
            .execute()
            .data or []
        )
        if not (r.get("analysis_result") or {}).get("skipped")
    ]

    repos  = score_by_preference(repos, pattern)
    papers = (
        db.table("arxiv_papers")
        .select("*")
        .gte("published", (datetime.now(timezone.utc) - timedelta(days=WEEKLY_DAYS)).strftime("%Y-%m-%d"))
        .order("published", desc=True)
        .limit(20)
        .execute()
        .data or []
    )
    print(f"  📄 {len(papers)} ArXiv papers")

    print("  🤖 Writing personal briefing…")
    briefing = write_briefing(repos, papers, pattern, week_label)

    db.table("recommendations").upsert(
        {
            "week_label": week_label,
            "data": {
                "top_repos": [
                    {
                        "name":    r["repo_name"],
                        "url":     r.get("repo_url", ""),
                        "stars":   r.get("stars", 0),
                        "cat":     r.get("category", ""),
                        "score":   r.get("_score", 0),
                        "problem": (r.get("analysis_result") or {}).get("core_problem", ""),
                        "domain":  (r.get("analysis_result") or {}).get("ai_domain", ""),
                        "methods": (r.get("analysis_result") or {}).get("xai_methods", []),
                    }
                    for r in repos[:INSIGHT_TOP_REPOS]
                ],
                "pattern":        pattern,
                "liked_count":    len(liked),
                "disliked_count": len(disliked),
            },
            "groq_analysis": briefing,
        },
        on_conflict="week_label",
    ).execute()
    print(f"🎉 Saved insight for {week_label}.")


if __name__ == "__main__":
    run()
