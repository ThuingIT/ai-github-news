"""
utils/metrics.py — Shared metrics calculation.
Used by both trend_analysis.py (daily) and weekly_compare.py (weekly)
to eliminate the duplicate calc_metrics() implementations.
"""
from collections import Counter
from utils.scoring import composite_score
from config import XAI_METHOD_TOP_N, DOMAIN_TOP_N, TOP_STARS_N


def calc_metrics(repos: list[dict]) -> dict:
    """
    Compute a metrics dict from a list of non-skipped repo rows.
    Returns:
        total, avg_score, cat_split, top_stars, top_repos,
        xai_methods, domains
    """
    if not repos:
        return {
            "total": 0, "avg_score": 0,
            "cat_split": {}, "top_stars": [],
            "top_repos": [], "xai_methods": [], "domains": [],
        }

    # Annotate scores in place
    for r in repos:
        analysis = r.get("analysis_result") or {}
        stars    = r.get("stars", 0) or 0
        rel      = analysis.get("relevance_score", 0) or 0
        r["_score"] = composite_score(stars, rel)

    # Rankings
    by_stars = sorted(repos, key=lambda r: r.get("stars", 0), reverse=True)
    by_score = sorted(repos, key=lambda r: r["_score"],        reverse=True)

    # XAI methods frequency
    xai_counter = Counter()
    for r in repos:
        for m in (r.get("analysis_result") or {}).get("xai_methods") or []:
            if m:
                xai_counter[m.strip()] += 1

    # AI domain frequency
    dom_counter = Counter()
    for r in repos:
        d = (r.get("analysis_result") or {}).get("ai_domain", "")
        if d:
            dom_counter[d] += 1

    # Avg relevance score
    scores  = [
        ((r.get("analysis_result") or {}).get("relevance_score") or 0)
        for r in repos
    ]
    avg_scr = round(sum(scores) / len(scores), 1) if scores else 0

    return {
        "total":       len(repos),
        "avg_score":   avg_scr,
        "cat_split":   dict(Counter(r.get("category", "") for r in repos)),
        "top_stars":   [_repo_summary(r) for r in by_stars[:TOP_STARS_N]],
        "top_repos":   [_repo_summary(r) for r in by_score[:TOP_STARS_N]],
        "xai_methods": [
            {"method": k, "count": v}
            for k, v in xai_counter.most_common(XAI_METHOD_TOP_N)
        ],
        "domains": [
            {"domain": k, "count": v}
            for k, v in dom_counter.most_common(DOMAIN_TOP_N)
        ],
    }


def _repo_summary(r: dict) -> dict:
    a = r.get("analysis_result") or {}
    return {
        "name":    r.get("repo_name", ""),
        "url":     r.get("repo_url", ""),
        "stars":   r.get("stars", 0),
        "score":   r.get("_score", 0),
        "cat":     r.get("category", ""),
        "problem": a.get("core_problem", ""),
        "innov":   a.get("key_innovation") or a.get("novelty") or "",
        "domain":  a.get("ai_domain", ""),
        "methods": a.get("xai_methods") or [],
        "rel":     a.get("relevance_score", 0),
        "why":     a.get("why_trending", ""),
    }
