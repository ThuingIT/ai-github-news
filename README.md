# ⬡ AI Hub

🌐 **Live Dashboard:** `https://thuingit.github.io/ai-github-news`

---

## Tổng quan

Thay vì quản lý 3 repo riêng biệt, **AI Hub** chạy toàn bộ hệ thống từ một nơi:

| Tab | Nội dung | Cập nhật |
|---|---|---|
| **Repos** | Card grid toàn bộ repos đã phân tích, filter theo category/score | Hàng ngày 8:00 |
| **Weekly** | Báo cáo xu hướng AI theo tuần, phân tích bởi Groq LLaMA | Thứ Hai 9:00 |
| **Insight** | Personal feed dựa trên preference, papers ArXiv liên quan | Thứ Hai 9:30 |

---

## Kiến trúc

```
GitHub Actions
├── daily_pipeline.yml        (8:00 GMT+7, mỗi ngày)
│   ├── fetch_repos.py        → GitHub API → Supabase
│   ├── analyze_repos.py      → Gemini 2.5 Flash
│   ├── trend_analysis.py     → Trend metrics
│   └── export_all.py         → GitHub Pages
│
├── weekly_pipeline.yml       (9:00 GMT+7, thứ Hai)
│   ├── weekly_compare.py     → Groq LLaMA 3.3 70B
│   └── export_all.py         → GitHub Pages
│
└── insight_pipeline.yml      (9:30 GMT+7, thứ Hai)
    ├── arxiv_fetch.py        → ArXiv API
    ├── insight_engine.py     → Groq LLaMA 3.3 70B
    └── export_all.py         → GitHub Pages
```

**Tất cả pipeline đều export cùng một `index.html`** — 3 tabs, 1 trang duy nhất.

---

## Cấu trúc repo

```
ai-github-news/
│
├── config.py               # Tất cả constants (model, tables, thresholds)
│
├── utils/
│   ├── db.py               # Supabase client (singleton)
│   ├── scoring.py          # Composite score logic
│   ├── metrics.py          # Shared metrics calculation
│   └── markdown.py         # Markdown → HTML converter
│
├── fetch_repos.py          # Job 1 (daily): GitHub API → Supabase
├── analyze_repos.py        # Job 2 (daily): Gemini analysis
├── trend_analysis.py       # Job 3 (daily): Weekly trend metrics
├── weekly_compare.py       # Job 1 (weekly): Groq narrative
├── arxiv_fetch.py          # Job 1 (insight): ArXiv papers
├── insight_engine.py       # Job 2 (insight): Personalized feed
├── export_all.py           # Final job (all pipelines): HTML export
│
├── requirements.txt
│
└── .github/
    └── workflows/
        ├── daily_pipeline.yml
        ├── weekly_pipeline.yml
        └── insight_pipeline.yml
```

---

## Cài đặt

### 1. Clone repo

```bash
git clone https://github.com/thuingit/ai-github-news.git
cd ai-github-news
pip install -r requirements.txt
```

### 2. Tạo bảng Supabase

Chạy SQL trong **Supabase → SQL Editor**:

```sql
-- Repos chính
CREATE TABLE ai_repos (
  id              serial PRIMARY KEY,
  repo_name       text UNIQUE,
  repo_url        text,
  description     text,
  stars           int,
  topics          text[],
  category        text,
  readme_url      text,
  analysis_result jsonb,
  created_at      timestamptz DEFAULT now()
);

-- Trend theo tuần
CREATE TABLE trend_data (
  id          serial PRIMARY KEY,
  week_label  text UNIQUE,
  data        jsonb,
  created_at  timestamptz DEFAULT now()
);

-- Báo cáo tuần
CREATE TABLE weekly_reports (
  id            serial PRIMARY KEY,
  week_label    text UNIQUE,
  data          jsonb,
  groq_analysis text,
  created_at    timestamptz DEFAULT now()
);

-- ArXiv papers
CREATE TABLE arxiv_papers (
  id           serial PRIMARY KEY,
  arxiv_id     text UNIQUE,
  title        text,
  abstract     text,
  authors      text[],
  published    text,
  url          text,
  keywords     text[],
  linked_repos text[],
  created_at   timestamptz DEFAULT now()
);

-- Personal recommendations
CREATE TABLE recommendations (
  id            serial PRIMARY KEY,
  week_label    text UNIQUE,
  data          jsonb,
  groq_analysis text,
  created_at    timestamptz DEFAULT now()
);

-- User preferences (like/dislike)
CREATE TABLE repo_preferences (
  id         serial PRIMARY KEY,
  repo_name  text UNIQUE,
  repo_url   text,
  liked      boolean,
  created_at timestamptz DEFAULT now()
);
```

### 3. GitHub Secrets

**Settings → Secrets and variables → Actions:**

| Secret | Mô tả |
|---|---|
| `GIT_TOKEN` | GitHub Personal Access Token (read:public_repo) |
| `SUPABASE_URL` | URL project Supabase |
| `SUPABASE_KEY` | Anon key Supabase |
| `GEMINI_API_KEY` | Google Gemini API key |
| `GROQ_API_KEY` | Groq API key ([console.groq.com](https://console.groq.com)) |

### 4. Bật GitHub Pages

```
Settings → Pages → Source → Deploy from branch → gh-pages → Save
```

### 5. Chạy lần đầu

```
Actions → Daily Pipeline → Run workflow
Actions → Weekly Pipeline → Run workflow
Actions → Insight Pipeline → Run workflow
```

---

## Pipelines

### Daily (8:00 AM GMT+7)

| Job | Script | Mô tả |
|---|---|---|
| fetch | `fetch_repos.py` | Quét GitHub API: XAI + Trending AI |
| analyze | `analyze_repos.py` | Gemini 2.5 Flash phân tích từng repo |
| trend | `trend_analysis.py` | Tính trend metrics 4 tuần |
| export | `export_all.py` | Xuất dashboard → GitHub Pages |

> **Tip:** Workflow có `skip_fetch` input — nếu bật, bỏ qua job fetch (chạy lại analyze nhanh hơn).

### Weekly (9:00 AM GMT+7, thứ Hai)

| Job | Script | Mô tả |
|---|---|---|
| compare | `weekly_compare.py` | So sánh tuần, Groq viết narrative |
| export | `export_all.py` | Xuất dashboard → GitHub Pages |

### Insight (9:30 AM GMT+7, thứ Hai)

| Job | Script | Mô tả |
|---|---|---|
| arxiv | `arxiv_fetch.py` | Fetch ArXiv papers từ keywords của repos |
| engine | `insight_engine.py` | Personalized feed + Groq briefing |
| export | `export_all.py` | Xuất dashboard → GitHub Pages |

---

## Composite Score

```
Score = Star Points (0–50) + Relevance Points (0–50)

Star Points   = log10(stars + 1) / log10(10001) × 50
Relevance Pts = (relevance_score / 10) × 50
```

| Score | Ý nghĩa |
|---|---|
| ≥ 70 🟢 | Xuất sắc |
| 40–70 🟡 | Tốt |
| < 40 🔴 | Trung bình |

---

## Tech Stack

| Thành phần | Công nghệ |
|---|---|
| Data source | GitHub Search API + ArXiv API |
| Database | Supabase (PostgreSQL) |
| Daily AI | Google Gemini 2.5 Flash |
| Weekly AI | Groq · LLaMA 3.3 70B Versatile |
| Automation | GitHub Actions |
| Frontend | HTML/CSS/JS tĩnh — 1 file duy nhất |
| Hosting | GitHub Pages |
| Language | Python 3.11 |

---

## Thay đổi so với phiên bản cũ (3 repos)

| Trước | Sau |
|---|---|
| 3 repos riêng biệt | 1 repo duy nhất |
| 3 dashboards HTML riêng | 1 HTML với 3 tabs |
| Logic trùng lặp (metrics, scoring, md→html) | `utils/` dùng chung |
| Constants rải rác | `config.py` tập trung |
| Không có `workflow_dispatch` input | `skip_fetch` option cho daily |
| `export_*.py` riêng từng pipeline | `export_all.py` dùng chung |

---

<div align="center">
  <sub>Built with ❤️ · Powered by GitHub Actions + Gemini + Groq + Supabase</sub>
</div>
