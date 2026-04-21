"""
weekly_compare.py — Compare this week vs last, call Groq for narrative.
Runs as job 1 of weekly_pipeline.yml.
"""
import os
from datetime import datetime, timezone, timedelta

from groq import Groq

from utils.db import get_client
from utils.metrics import calc_metrics
from config import (
    GROQ_MODEL, GROQ_TEMPERATURE, GROQ_MAX_TOKENS, WEEKLY_DAYS,
)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("❌ GROQ_API_KEY not set.")
    exit(1)

groq_client = Groq(api_key=GROQ_API_KEY)


# ── Data fetching ──────────────────────────────────────────────────────────────

def _fetch_repos_in_range(db, days_start: int, days_end: int) -> list[dict]:
    now   = datetime.now(timezone.utc)
    start = (now - timedelta(days=days_end)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end   = (now - timedelta(days=days_start)).strftime("%Y-%m-%dT%H:%M:%SZ")
    resp  = (
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


# ── Groq narrative ─────────────────────────────────────────────────────────────

def _fmt_repos(repos: list[dict]) -> str:
    lines = []
    for r in repos:
        lines.append(
            f"- [{r['name'].split('/')[-1]}]({r['url']}) | "
            f"⭐{r['stars']} | score {r['score']} | {r['cat']}\n"
            f"  Vấn đề: {r['problem']}\n"
            f"  Điểm mới: {r['innov'] or r['why']}"
        )
    return "\n".join(lines)


def _fmt_list(items: list[dict], k: str, v: str) -> str:
    return ", ".join(f"{i[k]} ({i[v]})" for i in items) or "Không có"


def call_groq(curr: dict, prev: dict, week_label: str) -> str:
    delta_total = curr["total"] - prev["total"]
    delta_score = round((curr["avg_score"] or 0) - (prev["avg_score"] or 0), 1)

    context = f"""
# Dữ liệu tuần {week_label}

| Chỉ số | Tuần trước | Tuần này | Δ |
|---|---|---|---|
| Tổng repos | {prev['total']} | {curr['total']} | {delta_total:+} |
| Avg score  | {prev['avg_score']} | {curr['avg_score']} | {delta_score:+} |
| XAI repos  | {prev['cat_split'].get('XAI', 0)} | {curr['cat_split'].get('XAI', 0)} | — |
| Trending   | {prev['cat_split'].get('Trending AI', 0)} | {curr['cat_split'].get('Trending AI', 0)} | — |

## Top repos (composite score)
{_fmt_repos(curr['top_repos'])}

## XAI Methods
- Tuần trước: {_fmt_list(prev['xai_methods'], 'method', 'count')}
- Tuần này:   {_fmt_list(curr['xai_methods'], 'method', 'count')}

## AI Domains
- Tuần trước: {_fmt_list(prev['domains'], 'domain', 'count')}
- Tuần này:   {_fmt_list(curr['domains'], 'domain', 'count')}

## Top Stars
{_fmt_repos(curr['top_stars'][:3])}
"""

    resp = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Bạn là chuyên gia phân tích xu hướng AI, viết tiếng Việt. "
                    "Phong cách: sâu sắc, rõ ràng, có chính kiến — không liệt kê khô khan. "
                    "Viết như nhà phân tích thực sự, không phải chatbot."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Từ dữ liệu sau, viết báo cáo xu hướng AI tuần {week_label}:\n{context}\n\n"
                    "Cấu trúc (markdown):\n\n"
                    "## 🔭 Bức tranh tuần này\n(2-3 câu tóm tắt — không liệt kê số liệu thô)\n\n"
                    "## 📈 So với tuần trước\n(Phân tích thay đổi — tại sao? Ý nghĩa là gì?)\n\n"
                    "## 🔬 Xu hướng XAI\n(Method nào nổi? Tại sao?)\n\n"
                    "## 🌐 Xu hướng AI tổng thể\n(Domain nào dẫn đầu? Dịch chuyển đáng chú ý?)\n\n"
                    "## 💡 Repo đáng chú ý\n(Chọn 1-2 repo, giải thích tại sao quan trọng)\n\n"
                    "## 🔮 Dự đoán tuần tới\n(1-2 câu có căn cứ)"
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
    print(f"📊 Weekly compare — {week_label}")

    curr_repos = _fetch_repos_in_range(db, 0, WEEKLY_DAYS)
    prev_repos = _fetch_repos_in_range(db, WEEKLY_DAYS, WEEKLY_DAYS * 2)
    print(f"  This week:  {len(curr_repos)} repos")
    print(f"  Last week:  {len(prev_repos)} repos")

    curr = calc_metrics(curr_repos)
    prev = calc_metrics(prev_repos)

    if prev["total"] == 0:
        print("  ⚠️  No prior week data — using 14-30 day baseline")
        prev = calc_metrics(_fetch_repos_in_range(db, WEEKLY_DAYS * 2, WEEKLY_DAYS * 4))

    print("  🤖 Calling Groq…")
    analysis = call_groq(curr, prev, week_label)
    print("  ✅ Groq done.")

    db.table("weekly_reports").upsert(
        {
            "week_label":    week_label,
            "data":          {"curr": curr, "prev": prev},
            "groq_analysis": analysis,
        },
        on_conflict="week_label",
    ).execute()
    print(f"🎉 Weekly report saved for {week_label}.")


if __name__ == "__main__":
    run()
