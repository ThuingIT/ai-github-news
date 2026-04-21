# ⬡ AI Hub

Hệ thống tự động theo dõi, phân tích và trực quan hoá xu hướng AI từ GitHub và ArXiv — gộp từ **ai-tracker**, **ai-weekly**, và **ai-insight** thành một repo duy nhất với một dashboard.

[![Daily Pipeline](https://github.com/YOUR_USERNAME/ai-hub/actions/workflows/daily_pipeline.yml/badge.svg)](https://github.com/YOUR_USERNAME/ai-hub/actions/workflows/daily_pipeline.yml)
[![Weekly Pipeline](https://github.com/YOUR_USERNAME/ai-hub/actions/workflows/weekly_pipeline.yml/badge.svg)](https://github.com/YOUR_USERNAME/ai-hub/actions/workflows/weekly_pipeline.yml)
[![Insight Pipeline](https://github.com/YOUR_USERNAME/ai-hub/actions/workflows/insight_pipeline.yml/badge.svg)](https://github.com/YOUR_USERNAME/ai-hub/actions/workflows/insight_pipeline.yml)

🌐 **Dashboard:** `https://YOUR_USERNAME.github.io/ai-hub`

---

## Dashboard

Một file `index.html` duy nhất với 3 tab:

| Tab | Nội dung |
|---|---|
| **Repos** | Card grid toàn bộ repos đã phân tích. Có search, filter theo category / domain / score, hiển thị đầy đủ: domain, tech stack, relevance bar, XAI methods, scope |
| **Weekly** | Báo cáo so sánh tuần viết bởi Groq LLaMA, kèm bar charts (XAI methods, AI domains, top stars, top by score) và KPIs có delta |
| **Insight** | Personal feed được xếp hạng theo preference, papers ArXiv liên kết với repos, và weekly briefing cá nhân hoá |

---

## Kiến trúc

```
GitHub Actions
│
├── daily_pipeline.yml          8:00 AM GMT+7 · mỗi ngày
│   ├─ fetch_repos.py           GitHub Search API → Supabase
│   ├─ analyze_repos.py         Gemini 2.5 Flash → phân tích README
│   ├─ trend_analysis.py        Tính trend metrics 4 tuần
│   └─ export_all.py            Supabase → index.html → GitHub Pages
│
├── weekly_pipeline.yml         9:00 AM GMT+7 · mỗi thứ Hai
│   ├─ weekly_compare.py        So sánh tuần + Groq LLaMA narrative
│   └─ export_all.py            → GitHub Pages
│
└── insight_pipeline.yml        9:30 AM GMT+7 · mỗi thứ Hai
    ├─ arxiv_fetch.py           ArXiv API → papers liên quan
    ├─ insight_engine.py        Personalised feed + Groq briefing
    └─ export_all.py            → GitHub Pages
```

**`export_all.py` là entry point cuối chung cho cả 3 pipeline** — nó đọc toàn bộ data từ Supabase và render 1 HTML duy nhất.

---

## Cấu trúc repo

```
ai-hub/
├── config.py               Tất cả constants: models, tables, thresholds, queries
├── requirements.txt
│
├── utils/
│   ├── db.py               Supabase singleton client
│   ├── scoring.py          Composite score (log10 stars + relevance)
│   ├── metrics.py          calc_metrics() — dùng chung daily + weekly
│   └── markdown.py         Markdown → HTML (cho Groq output)
│
├── fetch_repos.py          [daily-1] GitHub Search API
├── analyze_repos.py        [daily-2] Gemini phân tích README
├── trend_analysis.py       [daily-3] Trend metrics → Supabase
├── weekly_compare.py       [weekly-1] So sánh + Groq narrative
├── arxiv_fetch.py          [insight-1] ArXiv papers
├── insight_engine.py       [insight-2] Personalised feed + briefing
├── export_all.py           [all pipelines] HTML export
│
└── .github/workflows/
    ├── daily_pipeline.yml
    ├── weekly_pipeline.yml
    └── insight_pipeline.yml
```

---

## Cài đặt

### 1. Tạo repo và clone

```bash
git clone https://github.com/YOUR_USERNAME/ai-hub.git
cd ai-hub
pip install -r requirements.txt
```

### 2. Tạo bảng Supabase

Vào **Supabase → SQL Editor** và chạy:

```sql
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

CREATE TABLE trend_data (
  id         serial PRIMARY KEY,
  week_label text UNIQUE,
  data       jsonb,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE weekly_reports (
  id            serial PRIMARY KEY,
  week_label    text UNIQUE,
  data          jsonb,
  groq_analysis text,
  created_at    timestamptz DEFAULT now()
);

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

CREATE TABLE recommendations (
  id            serial PRIMARY KEY,
  week_label    text UNIQUE,
  data          jsonb,
  groq_analysis text,
  created_at    timestamptz DEFAULT now()
);

CREATE TABLE repo_preferences (
  id         serial PRIMARY KEY,
  repo_name  text UNIQUE,
  repo_url   text,
  liked      boolean,
  created_at timestamptz DEFAULT now()
);
```

### 3. GitHub Secrets

**Settings → Secrets and variables → Actions → New repository secret:**

| Secret | Mô tả |
|---|---|
| `GIT_TOKEN` | GitHub Personal Access Token — scope: `public_repo` |
| `SUPABASE_URL` | URL project Supabase (ví dụ: `https://xxx.supabase.co`) |
| `SUPABASE_KEY` | Anon/service key Supabase |
| `GEMINI_API_KEY` | Google Gemini API key |
| `GROQ_API_KEY` | Groq API key — tạo tại [console.groq.com](https://console.groq.com) |

### 4. Bật GitHub Pages

```
Settings → Pages → Source: Deploy from branch → Branch: gh-pages → Save
```

### 5. Chạy lần đầu

```
Actions → Daily Pipeline   → Run workflow
Actions → Weekly Pipeline  → Run workflow
Actions → Insight Pipeline → Run workflow
```

---

## Pipelines

### Daily — `daily_pipeline.yml`

Chạy 8:00 AM GMT+7 mỗi ngày. Có thể trigger thủ công với option **`skip_fetch`** (bỏ qua bước fetch, chạy lại analyze nhanh hơn).

| Job | Script | Mô tả |
|---|---|---|
| `fetch` | `fetch_repos.py` | Quét GitHub: categories XAI + Trending AI |
| `analyze` | `analyze_repos.py` | Gemini 2.5 Flash đọc README, trả JSON |
| `trend` | `trend_analysis.py` | Tính metrics 4 tuần, upsert vào Supabase |
| `export` | `export_all.py` | Render dashboard → push gh-pages |

### Weekly — `weekly_pipeline.yml`

Chạy 9:00 AM GMT+7 mỗi thứ Hai.

| Job | Script | Mô tả |
|---|---|---|
| `compare` | `weekly_compare.py` | So sánh tuần này vs tuần trước, Groq viết phân tích |
| `export` | `export_all.py` | Render dashboard → push gh-pages |

### Insight — `insight_pipeline.yml`

Chạy 9:30 AM GMT+7 mỗi thứ Hai (sau weekly).

| Job | Script | Mô tả |
|---|---|---|
| `arxiv` | `arxiv_fetch.py` | Fetch papers từ ArXiv dựa trên keywords của repos |
| `engine` | `insight_engine.py` | Xếp hạng repos theo preference, Groq viết briefing |
| `export` | `export_all.py` | Render dashboard → push gh-pages |

---

## Composite Score

```
Score (0–100) = Star Points (0–50) + Relevance Points (0–50)

Star Points   = log10(stars + 1) / log10(10001) × 50
Relevance Pts = (gemini_relevance_score / 10) × 50
```

| Range | Màu | Ý nghĩa |
|---|---|---|
| ≥ 70 | 🟢 xanh | Repo xuất sắc, rất đáng theo dõi |
| 40–69 | 🟡 vàng | Tốt, phù hợp với nhiều trường hợp |
| < 40 | 🔴 đỏ | Trung bình hoặc kém liên quan |

> Lưu ý: Tab Insight dùng điểm cá nhân hoá (có thể vượt 100 do bonus preference). Dashboard hiển thị tối đa 100.

---

## Tech Stack

| Thành phần | Chi tiết |
|---|---|
| Data sources | GitHub Search API · ArXiv API |
| Database | Supabase (PostgreSQL) |
| Daily analysis | Google Gemini 2.5 Flash |
| Weekly / Insight AI | Groq · LLaMA 3.3 70B Versatile |
| Automation | GitHub Actions (3 workflows) |
| Frontend | Static HTML/CSS/JS — 1 file, 0 dependencies |
| Hosting | GitHub Pages |
| Language | Python 3.11 |

---

## Chạy local

```bash
# Setup
cp .env.example .env   # điền các API keys
source .env

# Chạy từng bước
python fetch_repos.py
python analyze_repos.py
python trend_analysis.py
python export_all.py

# Xem kết quả
open output/index.html
```

---

## Thay đổi so với 3 repos cũ

| Trước | Sau |
|---|---|
| 3 repos, 3 dashboards HTML riêng | 1 repo, 1 HTML với 3 tabs |
| `calc_metrics()` viết 2 lần | `utils/metrics.py` dùng chung |
| `composite_score()` viết 4 lần | `utils/scoring.py` dùng chung |
| `md_to_html()` viết 3 lần | `utils/markdown.py` dùng chung |
| Constants rải rác nhiều file | `config.py` tập trung |
| 3 file `export_*.py` | `export_all.py` duy nhất |
| Không có `workflow_dispatch` input | Daily có `skip_fetch` option |
| Score Insight vượt 100 hiển thị raw | Clamp về 100 khi render |
| Chữ analysis prose quá mờ | Font size tăng, contrast rõ hơn |
| Không có search | Search bar + filter domain/score |

---

<div align="center">
  <sub>Built with GitHub Actions · Gemini · Groq · Supabase · GitHub Pages</sub>
</div>
