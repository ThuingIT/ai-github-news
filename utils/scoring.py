"""
utils/scoring.py — Composite score calculation, shared across all scripts.
"""
import math
from config import SCORE_STAR_MAX, SCORE_REL_MAX, SCORE_STAR_CEILING, SCORE_THRESHOLDS


def composite_score(stars: int, relevance_score: int | float) -> float:
    """
    Score = Star Points (0–50) + Relevance Points (0–50)

    Star Points   = log10(stars + 1) / log10(CEILING) × 50
    Relevance Pts = (relevance_score / 10) × 50
    """
    star_pts = min(
        math.log10(stars + 1) / math.log10(SCORE_STAR_CEILING) * SCORE_STAR_MAX,
        SCORE_STAR_MAX,
    )
    rel_pts = (relevance_score / 10) * SCORE_REL_MAX
    return round(star_pts + rel_pts, 1)


def score_from_repo(repo: dict) -> float:
    """Convenience wrapper — accepts a raw Supabase row dict."""
    analysis = repo.get("analysis_result") or {}
    if analysis.get("skipped"):
        return 0.0
    stars = repo.get("stars", 0) or 0
    rel   = analysis.get("relevance_score", 0) or 0
    return composite_score(stars, rel)


def score_label(score: float) -> str:
    """Return emoji label for a composite score."""
    if score >= SCORE_THRESHOLDS["high"]:
        return "🟢"
    if score >= SCORE_THRESHOLDS["mid"]:
        return "🟡"
    return "🔴"


def score_color(score: float) -> str:
    """Return CSS hex color for a composite score."""
    if score >= SCORE_THRESHOLDS["high"]:
        return "#4ade80"
    if score >= SCORE_THRESHOLDS["mid"]:
        return "#fbbf24"
    return "#f87171"
