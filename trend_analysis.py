"""
trend_analysis.py — Calculate weekly trend metrics and upsert into Supabase.
Runs as job 3 of daily_pipeline.yml.
"""
from datetime import datetime, timezone, timedelta

from utils.db import get_client
from utils.metrics import calc_metrics
from config import TREND_WEEKS


# ── Date helpers ───────────────────────────────────────────────────────────────

def _week_label(weeks_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(weeks=weeks_ago)).strftime("%Y-W%W")


def _week_range(weeks_ago: int = 0) -> tuple[str, str]:
    now   = datetime.now(timezone.utc)
    start = now - timedelta(weeks=weeks_ago, days=now.weekday())
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end   = start + timedelta(days=7)
    fmt   = "%Y-%m-%dT%H:%M:%SZ"
    return start.strftime(fmt), end.strftime(fmt)


def _fetch_repos_in_week(db, weeks_ago: int = 0) -> list[dict]:
    start, end = _week_range(weeks_ago)
    resp = (
        db.table("ai_repos")
        .select("*")
        .gte("created_at", start)
        .lt("created_at", end)
        .not_.is_("analysis_result", "null")
        .execute()
    )
    return [
        r for r in (resp.data or [])
        if not (r.get("analysis_result") or {}).get("skipped")
    ]


# ── Delta ──────────────────────────────────────────────────────────────────────

def _compare(curr: dict, prev: dict) -> dict:
    return {
        "total_delta":     curr.get("total", 0) - prev.get("total", 0),
        "avg_score_delta": round(
            (curr.get("avg_score") or 0) - (prev.get("avg_score") or 0), 1
        ),
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def run() -> None:
    db = get_client()
    print("📊 Calculating trend data…")

    weeks_data: list[dict] = []
    for w in range(TREND_WEEKS):
        label = _week_label(w)
        repos = _fetch_repos_in_week(db, w)
        print(f"  Week {label}: {len(repos)} repos")
        metrics = calc_metrics(repos)
        metrics["week_label"] = label
        weeks_data.append(metrics)

    # Attach delta (current vs previous week)
    if len(weeks_data) >= 2:
        weeks_data[0]["delta"] = _compare(weeks_data[0], weeks_data[1])

    for w in weeks_data:
        label = w["week_label"]
        try:
            db.table("trend_data").upsert(
                {"week_label": label, "data": w},
                on_conflict="week_label",
            ).execute()
            print(f"  ✅ Saved week {label}")
        except Exception as e:
            print(f"  ✗ Error saving {label}: {e}")

    print("🎉 Trend analysis complete.")


if __name__ == "__main__":
    run()
