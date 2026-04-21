# ============================================================
# config.py — Single source of truth for all constants
# ============================================================

# ── AI Models ──────────────────────────────────────────────
GEMINI_MODEL  = "gemini-2.5-flash"
GROQ_MODEL    = "llama-3.3-70b-versatile"

# ── Supabase Tables ────────────────────────────────────────
TABLE_REPOS        = "ai_repos"
TABLE_TRENDS       = "trend_data"
TABLE_WEEKLY       = "weekly_reports"
TABLE_ARXIV        = "arxiv_papers"
TABLE_RECS         = "recommendations"
TABLE_PREFS        = "repo_preferences"

# ── Fetch Config ───────────────────────────────────────────
FETCH_DAYS_WINDOW  = 30          # how many days back to fetch
XAI_MIN_STARS      = 20
TRENDING_MIN_STARS = 1000

GITHUB_QUERIES = [
    {"category": "XAI",         "topic": "explainable-ai"},
    {"category": "XAI",         "topic": "xai"},
    {"category": "Trending AI", "topic": "machine-learning"},
    {"category": "Trending AI", "topic": "ai"},
]

# ── Analysis Config ────────────────────────────────────────
README_MAX_CHARS   = 1000
GEMINI_RETRIES     = 3
GEMINI_RETRY_DELAY = 2          # seconds, multiplied by attempt

FILTER_KEYWORDS = {
    "XAI": [
        "explainab", "interpretab", "lime", "shap", "attention",
        "saliency", "attribution", "transparent", "xai",
        "feature importance", "counterfactual", "surrogate", "post-hoc",
    ],
    "Trending AI": [
        "model", "neural", "train", "dataset", "inference", "llm",
        "diffusion", "transformer", "benchmark", "finetune", "agent",
        "multimodal", "vision", "language", "generation",
    ],
}

PROMPTS = {
    "XAI": """\
Đọc README sau và trả về JSON (raw, không markdown):
{
  "is_survey_or_awesome_list": true/false,
  "core_problem": "1 câu mô tả bài toán",
  "xai_methods": [],
  "scope": "local | global | both",
  "model_agnostic": true/false,
  "novelty": "1 câu điểm mới",
  "relevance_score": 0-10,
  "tech_stack": []
}""",
    "Trending AI": """\
Đọc README sau và trả về JSON (raw, không markdown):
{
  "is_survey_or_awesome_list": true/false,
  "core_problem": "1 câu mô tả bài toán",
  "ai_domain": "CV | NLP | Multimodal | RL | GenAI | Audio | Other",
  "key_innovation": "1 câu đột phá chính",
  "real_world_applicable": true/false,
  "why_trending": "1 câu lý do repo hot",
  "relevance_score": 0-10,
  "tech_stack": []
}""",
}

# ── Scoring ────────────────────────────────────────────────
SCORE_STAR_MAX     = 50
SCORE_REL_MAX      = 50
SCORE_STAR_CEILING = 10001      # log10 normalisation ceiling

SCORE_THRESHOLDS = {"high": 70, "mid": 40}   # ≥70 green, 40-70 yellow, <40 red

# ── Trend Config ───────────────────────────────────────────
TREND_WEEKS        = 4
XAI_METHOD_TOP_N   = 8
DOMAIN_TOP_N       = 8
TOP_STARS_N        = 5

# ── ArXiv Config ───────────────────────────────────────────
ARXIV_MAX_RESULTS  = 5
ARXIV_QUERIES_MAX  = 6
ARXIV_DELAY        = 3          # seconds between requests
ARXIV_LINK_MIN     = 3          # min keyword overlap to link paper→repo

BASE_ARXIV_QUERIES = [
    "explainable artificial intelligence",
    "interpretable machine learning",
    "SHAP LIME neural network",
    "large language model survey",
    "transformer attention mechanism",
]

# ── Weekly / Insight ────────────────────────────────────────
WEEKLY_DAYS        = 7
INSIGHT_TOP_REPOS  = 10
GROQ_TEMPERATURE   = 0.7
GROQ_MAX_TOKENS    = 2048
