# PROJECT_CONTEXT.md — AI Hub (for Claude)

> **Hướng dẫn dùng file này:** Đây là file tổng quan dự án. Khi gửi cho Claude, Claude sẽ hiểu toàn bộ kiến trúc, luồng dữ liệu, và cách debug/phát triển mà không cần xem thêm file nào khác — trừ khi cần sửa code cụ thể (Claude sẽ yêu cầu file đó).

---

## 1. TỔNG QUAN

**Mục tiêu:** Tự động thu thập GitHub repos về AI/XAI mỗi ngày, phân tích bằng LLM, tổng hợp xu hướng, và xuất dashboard HTML lên GitHub Pages.

**Stack:** Python 3.11 · Supabase (PostgreSQL) · Gemini API · Groq API · GitHub Actions · GitHub Pages

**Output cuối cùng:** `output/index.html` — single-file dashboard với 3 tab: Repos / Weekly / Insight

---

## 2. KIẾN TRÚC — 3 PIPELINE

### Pipeline A: Daily (chạy 8:00 AM GMT+7, mỗi ngày)
```
fetch_repos.py → analyze_repos.py → trend_analysis.py → export_all.py → GitHub Pages
     Job 1            Job 2              Job 3               Job 4
```

### Pipeline B: Weekly (chạy 9:00 AM GMT+7, mỗi thứ Hai)
```
weekly_compare.py → export_all.py → GitHub Pages
      Job 1              Job 2
```

### Pipeline C: Insight (chạy 9:30 AM GMT+7, mỗi thứ Hai, sau Weekly)
```
arxiv_fetch.py → insight_engine.py → export_all.py → GitHub Pages
    Job 1             Job 2               Job 3
```

---

## 3. DATABASE SCHEMA (Supabase)

| Table | PK / Unique | Mô tả |
|-------|-------------|-------|
| `ai_repos` | `id` (auto), unique `repo_name` | Repos từ GitHub, có cột `analysis_result` (JSONB, null = chưa phân tích) |
| `trend_data` | `week_label` (e.g. "2025-W20") | Metrics tổng hợp theo tuần |
| `weekly_reports` | `week_label` | So sánh tuần này vs tuần trước + Groq narrative |
| `arxiv_papers` | `arxiv_id` | Papers từ ArXiv |
| `recommendations` | `week_label` | Personal feed + insight briefing |
| `repo_preferences` | `repo_name` | User like/dislike (từ UI) |

### Cấu trúc `analysis_result` (JSONB trong `ai_repos`)

**XAI repos:**
```json
{
  "is_survey_or_awesome_list": false,
  "core_problem": "string",
  "xai_methods": ["SHAP", "LIME"],
  "scope": "local | global | both",
  "model_agnostic": true,
  "novelty": "string",
  "relevance_score": 8,
  "tech_stack": ["PyTorch"],
  "_meta": { "category": "XAI", "analyzed_at": "...", "input_chars": 1200 }
}
```

**Trending AI repos:**
```json
{
  "is_survey_or_awesome_list": false,
  "core_problem": "string",
  "ai_domain": "CV | NLP | Multimodal | RL | GenAI | Audio | Other",
  "key_innovation": "string",
  "real_world_applicable": true,
  "why_trending": "string",
  "relevance_score": 7,
  "tech_stack": ["PyTorch", "HuggingFace"],
  "_meta": { ... }
}
```

**Skipped repos:**
```json
{ "skipped": true, "reason": "no_keyword_match | survey_or_awesome_list", "category": "XAI" }
```

---

## 4. FILE MAP

```
repo/
├── config.py              # ← MỌI HẰNG SỐ ở đây (models, thresholds, queries, prompts)
├── fetch_repos.py         # GitHub Search API → ai_repos table
├── analyze_repos.py       # Gemini phân tích README → analysis_result
├── trend_analysis.py      # Tính metrics theo tuần → trend_data table
├── weekly_compare.py      # So sánh 2 tuần + Groq narrative → weekly_reports
├── arxiv_fetch.py         # ArXiv API → arxiv_papers table
├── insight_engine.py      # User preferences + scoring → recommendations
├── export_all.py          # Đọc tất cả tables → output/index.html
├── requirements.txt       # requests, supabase, google-genai, groq
└── utils/
    ├── db.py              # get_client() — Supabase singleton
    ├── scoring.py         # composite_score(), score_color(), score_from_repo()
    ├── metrics.py         # calc_metrics(repos) — dùng chung cho trend + weekly
    └── markdown.py        # md_to_html() — markdown đơn giản → HTML
```

---

## 5. SCORING FORMULA

```
Composite Score (0–100) = Star Points (0–50) + Relevance Points (0–50)

Star Points   = log10(stars + 1) / log10(10001) × 50
Relevance Pts = (relevance_score / 10) × 50

Màu sắc: ≥70 → xanh (#4ade80) | 40-69 → vàng (#fbbf24) | <40 → đỏ (#f87171)
```

Trong `insight_engine.py`, score có thể vượt 100 do personalisation bonus (+30 domain, +20 cat, +15/method). UI clamp về 100 khi hiển thị.

---

## 6. CONFIG.PY — QUICK REFERENCE

| Hằng số | Giá trị | Ý nghĩa |
|---------|---------|---------|
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model phân tích README |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Model viết narrative |
| `FETCH_DAYS_WINDOW` | 30 | Fetch repos tạo trong 30 ngày qua |
| `XAI_MIN_STARS` | 20 | Stars tối thiểu cho XAI repos |
| `TRENDING_MIN_STARS` | 1000 | Stars tối thiểu cho Trending repos |
| `README_MAX_CHARS` | 1000 | Giới hạn README gửi cho Gemini |
| `GEMINI_RETRIES` | 3 | Retry khi Gemini fail |
| `ARXIV_MAX_RESULTS` | 5 | Số papers mỗi query ArXiv |
| `ARXIV_QUERIES_MAX` | 6 | Số queries ArXiv tối đa |
| `INSIGHT_TOP_REPOS` | 10 | Số repos trong personal feed |
| `SCORE_THRESHOLDS` | `{high:70, mid:40}` | Ngưỡng màu score |

**GitHub queries** (trong `GITHUB_QUERIES`):
- `XAI` ← topic: `explainable-ai`, `xai`
- `Trending AI` ← topic: `machine-learning`, `ai`

---

## 7. LUỒNG DỮ LIỆU CHI TIẾT

### fetch_repos.py
- Gọi GitHub Search API với query: `topic:{t} created:>{since} stars:>{min}`
- Upsert vào `ai_repos` (skip nếu `duplicate key`)
- **Các field lưu:** repo_name, repo_url, description, stars, topics, category, readme_url

### analyze_repos.py
- Lấy repos có `analysis_result IS NULL`
- Pre-filter bằng keyword trong description/topics (tránh gọi Gemini vô ích)
- Fetch README từ `readme_url` (raw GitHub)
- Extract phần quan trọng của README (ưu tiên ## Method, ## Result, v.v.)
- Gọi Gemini → parse JSON → lưu vào `analysis_result`
- Skip nếu `is_survey_or_awesome_list: true`

### trend_analysis.py
- Tính metrics cho 4 tuần gần nhất (TREND_WEEKS=4)
- Mỗi tuần: total, avg_score, cat_split, top_stars, top_repos, xai_methods, domains
- Upsert vào `trend_data` theo `week_label`

### weekly_compare.py
- So sánh 7 ngày gần nhất vs 7-14 ngày trước
- Gọi Groq để viết narrative tiếng Việt
- Upsert vào `weekly_reports`

### arxiv_fetch.py
- Lấy keywords từ `analysis_result` của repos 30 ngày gần đây (xai_methods, ai_domain, tech_stack)
- Kết hợp với BASE_ARXIV_QUERIES
- Fetch ArXiv API, link papers với repos qua keyword overlap (≥3 từ trùng)
- Upsert vào `arxiv_papers`

### insight_engine.py
- Đọc `repo_preferences` (like/dislike từ UI)
- Gọi Groq phân tích pattern người dùng
- Score repos với personalisation bonus/penalty
- Gọi Groq viết personal briefing
- Upsert vào `recommendations`

### export_all.py
- Đọc tất cả 5 tables
- Build HTML đơn nhất với 3 tab
- Lưu `output/index.html`
- GitHub Actions deploy lên GitHub Pages

---

## 8. SECRETS CẦN THIẾT

| Secret | Dùng ở đâu |
|--------|-----------|
| `GIT_TOKEN` | fetch_repos.py (GitHub API) |
| `SUPABASE_URL` | utils/db.py |
| `SUPABASE_KEY` | utils/db.py |
| `GEMINI_API_KEY` | analyze_repos.py |
| `GROQ_API_KEY` | weekly_compare.py, insight_engine.py |

⚠️ `export_all.py` embed `SUPABASE_URL` và `SUPABASE_KEY` vào HTML output để JS gọi Supabase REST API (cho like/dislike). Chỉ dùng anon key, không dùng service key.

---

## 9. DEBUGGING GUIDE

### Khi pipeline fail, kiểm tra theo thứ tự:

**Job "Fetch repos" fail:**
- Kiểm tra secret `GIT_TOKEN` còn hiệu lực không (GitHub → Settings → Developer settings → Tokens)
- GitHub Search API rate limit: 10 req/min (unauthenticated: 1/min)
- Lỗi `duplicate key` là bình thường (đã có repo đó rồi)

**Job "Analyse with Gemini" fail:**
- `GEMINI_API_KEY` hết quota? → Xem Gemini dashboard
- README fetch timeout (10s) → Repo có README không? URL có đúng không?
- Gemini trả về text không phải JSON → `call_gemini()` đã handle retry 3 lần
- Nếu toàn bộ repos bị skip → kiểm tra `FILTER_KEYWORDS` trong config.py

**Job "Trend analysis" / "Weekly compare" fail:**
- Supabase connection error → kiểm tra `SUPABASE_URL`, `SUPABASE_KEY`
- `ai_repos` table rỗng hoặc không có data tuần đó → fetch/analyze chưa chạy

**Job "Export dashboard" fail:**
- `output/` directory không tạo được → permissions
- GitHub Pages deploy fail → kiểm tra branch `gh-pages` tồn tại chưa, và repo có bật Pages chưa

**Dashboard hiển thị "No data":**
- Tab Repos: `analysis_result` toàn null hoặc skipped → chạy lại analyze_repos.py
- Tab Weekly: `weekly_reports` table rỗng → chạy weekly_compare.py
- Tab Insight/Feed: `recommendations` table rỗng → chạy insight_engine.py

### Chạy thủ công (local debug):
```bash
# Setup
pip install -r requirements.txt
export SUPABASE_URL="..." SUPABASE_KEY="..." GEMINI_API_KEY="..." GROQ_API_KEY="..." GIT_TOKEN="..."

# Chạy từng bước
python fetch_repos.py
python analyze_repos.py
python trend_analysis.py
python weekly_compare.py
python arxiv_fetch.py
python insight_engine.py
python export_all.py
# → Mở output/index.html trong browser
```

### Workflow dispatch (skip fetch):
Vào GitHub Actions → Daily Pipeline → Run workflow → tick "Skip fetch_repos" để re-analyze mà không fetch lại.

---

## 10. ĐIỂM DỄ PHÁT TRIỂN / MỞ RỘNG

| Muốn làm | Sửa file nào | Ghi chú |
|----------|-------------|---------|
| Thêm GitHub topic mới | `config.py` → `GITHUB_QUERIES` | Thêm dict `{category, topic}` |
| Thêm category mới (e.g. "LLM Agents") | `config.py` → `FILTER_KEYWORDS`, `PROMPTS` + `export_all.py` → `DOMAIN_MAP`, CSS badges | 4 chỗ |
| Thay model Gemini | `config.py` → `GEMINI_MODEL` | |
| Thay model Groq | `config.py` → `GROQ_MODEL` | |
| Thay ngưỡng score màu | `config.py` → `SCORE_THRESHOLDS` | |
| Thêm field vào card | `export_all.py` → `render_repo_card()` + cập nhật prompt trong `config.py` | |
| Thêm chart/section vào Weekly tab | `export_all.py` → `render_weekly_tab()` | |
| Thêm filter button | `export_all.py` → toolbar HTML + `_applyFilters()` JS | |
| Thêm ArXiv query cố định | `config.py` → `BASE_ARXIV_QUERIES` | |
| Tăng tốc độ fetch | `config.py` → `ARXIV_DELAY`, `GEMINI_RETRY_DELAY` | Cẩn thận rate limit |
| Lưu thêm metadata | `fetch_repos.py` → dict `data` + thêm cột Supabase | |

---

## 11. GOTCHAS & LƯU Ý

- **`export_all.py` không cần chạy riêng** — nó được gọi ở cuối mỗi pipeline. Nhưng có thể chạy độc lập để re-export từ data đã có.
- **`keep_files: true`** trong GitHub Actions deploy — đảm bảo weekly/insight output không bị xóa khi daily chạy.
- **Insight pipeline chạy sau Weekly 30 phút** — để `weekly_reports` đã có data trước khi `insight_engine.py` đọc.
- **`composite_score` trong `scoring.py` dùng chung** — `trend_analysis`, `weekly_compare`, `insight_engine`, và `export_all` đều import từ đây. Nếu đổi công thức, tất cả update theo.
- **Supabase anon key trong HTML** là bình thường nếu đã cấu hình RLS (Row Level Security) đúng trên Supabase — chỉ cho phép đọc/ghi `repo_preferences`.
- **`analysis_result` là JSONB** — query Supabase bằng `.not_.is_("analysis_result", "null")` để lọc chưa phân tích.
- **Gemini prompt viết tiếng Việt** (`config.py` → `PROMPTS`) nhưng output thực tế là JSON field — không ảnh hưởng.
- **Groq narrative viết tiếng Việt** — nếu muốn đổi ngôn ngữ, sửa system prompt trong `weekly_compare.py` và `insight_engine.py`.

---

## 12. KHI NÀO CẦN YÊU CẦU THÊM FILE

Claude sẽ yêu cầu xem file cụ thể khi:
- **Sửa logic phân tích** → cần `analyze_repos.py`
- **Sửa scoring formula** → cần `utils/scoring.py`
- **Sửa UI/HTML** → cần `export_all.py` (file lớn ~500 dòng)
- **Thêm pipeline mới** → cần file `.github/workflows/` liên quan
- **Debug Supabase query** → cần `utils/db.py` hoặc file gọi query đó
- **Sửa metrics** → cần `utils/metrics.py`

Với task đơn giản như đổi config, thêm keyword, đổi model — **chỉ cần file này + config.py là đủ**.
