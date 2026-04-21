"""
export_all.py — Export a single index.html with all 3 dashboards.
Runs as the final job in each pipeline.

Tabs:
  1. Repos     — card grid, filter, composite score (daily)
  2. Weekly    — editorial report, week navigation (weekly)
  3. Insight   — personal feed, ArXiv papers, like/dislike (insight)
"""
import os
import json
import math
from datetime import datetime, timezone

from utils.db import get_client
from utils.markdown import md_to_html
from utils.scoring import score_from_repo, score_color
from config import TABLE_REPOS, TABLE_TRENDS, TABLE_WEEKLY, TABLE_ARXIV, TABLE_RECS

# ── Data fetching ──────────────────────────────────────────────────────────────

def fetch_all(db):
    repos = (
        db.table(TABLE_REPOS).select("*")
        .not_.is_("analysis_result", "null")
        .order("stars", desc=True)
        .execute().data or []
    )
    trends = (
        db.table(TABLE_TRENDS).select("*")
        .order("week_label", desc=True).limit(4)
        .execute().data or []
    )
    weekly = (
        db.table(TABLE_WEEKLY).select("*")
        .order("week_label", desc=True).limit(8)
        .execute().data or []
    )
    arxiv = (
        db.table(TABLE_ARXIV).select("*")
        .order("published", desc=True).limit(30)
        .execute().data or []
    )
    recs = (
        db.table(TABLE_RECS).select("*")
        .order("week_label", desc=True).limit(4)
        .execute().data or []
    )
    return repos, trends, weekly, arxiv, recs

# ── Helpers ────────────────────────────────────────────────────────────────────

def star_fmt(n: int) -> str:
    return f"{n/1000:.1f}k" if n >= 1000 else str(n)

DOMAIN_COLORS = {
    "GenAI": "#e879f9", "NLP": "#60a5fa", "CV": "#34d399",
    "Multimodal": "#a78bfa", "RL": "#fbbf24",
    "Audio": "#fb923c", "Other": "#94a3b8",
}

def domain_color(d: str) -> str:
    return DOMAIN_COLORS.get(d, "#94a3b8")

# ── Repos tab: card grid ───────────────────────────────────────────────────────

def render_repo_card(repo: dict) -> str:
    a     = repo.get("analysis_result") or {}
    if a.get("skipped"):
        return ""

    name    = repo.get("repo_name", "")
    url     = repo.get("repo_url", "#").replace("'", "\\'")
    stars   = repo.get("stars", 0) or 0
    cat     = repo.get("category", "")
    score   = repo.get("_score", 0)
    rel     = a.get("relevance_score", "?")
    problem = a.get("core_problem", "")
    domain  = a.get("ai_domain", "")
    methods = a.get("xai_methods", []) or []
    stack   = a.get("tech_stack", []) or []
    innov   = a.get("key_innovation") or a.get("novelty") or ""
    why     = a.get("why_trending", "")
    scope   = a.get("scope", "")
    agnostic = a.get("model_agnostic")
    real    = a.get("real_world_applicable")

    sc      = score_color(score)
    dc      = domain_color(domain)

    tags = "".join(f'<span class="tag">{t}</span>' for t in (methods + stack)[:5])

    pills = "".join(filter(None, [
        f'<span class="pill">{scope}</span>'        if scope else "",
        '<span class="pill">model-agnostic</span>'  if agnostic is True else "",
        '<span class="pill">real-world</span>'      if real is True else "",
    ]))

    domain_badge = (
        f'<span class="domain-badge" style="color:{dc};background:{dc}18">{domain}</span>'
        if domain else ""
    )
    cat_cls = "xai" if cat == "XAI" else "trend"

    return f'''<article class="card" onclick="window.open('{url}','_blank')" data-cat="{cat}" data-score="{score}">
  <header class="card-head">
    <div class="card-badges">
      <span class="cat-badge {cat_cls}">{cat}</span>
      {domain_badge}
    </div>
    <div class="score-chip" style="--sc:{sc}">{score}</div>
  </header>
  <h3 class="card-title">{name.split("/")[-1]}</h3>
  <p class="card-owner">{name.split("/")[0]}/</p>
  <p class="card-problem">{problem}</p>
  {"<p class='card-innov'>💡 " + innov + "</p>" if innov else ""}
  {"<p class='card-innov'>🔥 " + why   + "</p>" if why   else ""}
  {"<div class='pills'>" + pills + "</div>" if pills else ""}
  {"<div class='tags'>" + tags + "</div>"   if tags  else ""}
  <footer class="card-foot">
    <span class="stars">★ {star_fmt(stars)}</span>
    <span class="rel">relevance {rel}/10</span>
  </footer>
</article>'''

# ── Weekly tab ─────────────────────────────────────────────────────────────────

def render_weekly_tab(weekly: list) -> str:
    if not weekly:
        return '<p class="empty">No weekly reports yet — run weekly_compare.py first.</p>'

    latest      = weekly[0]
    week_label  = latest.get("week_label", "")
    data        = latest.get("data", {})
    curr        = data.get("curr", {})
    prev        = data.get("prev", {})
    analysis    = latest.get("groq_analysis", "")

    # sidebar week list
    sidebar = "".join(
        f'<button class="week-btn {"active" if i == 0 else ""}" '
        f'onclick="loadWeek({i})">{r["week_label"]}</button>'
        for i, r in enumerate(weekly)
    )

    all_data = json.dumps(
        [{"week_label": r["week_label"], "data": r.get("data", {}),
          "groq_analysis": r.get("groq_analysis", "")} for r in weekly],
        ensure_ascii=False,
    )

    def kpi(label, cv, pv, color):
        delta = cv - pv if isinstance(cv, (int, float)) and isinstance(pv, (int, float)) else None
        delta_html = ""
        if delta is not None:
            cls  = "up" if delta > 0 else ("down" if delta < 0 else "flat")
            sign = "+" if delta > 0 else ""
            delta_html = f'<span class="kpi-delta {cls}">{sign}{delta}</span>'
        return (
            f'<div class="kpi-card">'
            f'<div class="kpi-val" style="color:{color}">{cv}</div>'
            f'<div class="kpi-lbl">{label}</div>'
            f'{delta_html}'
            f'</div>'
        )

    def bars(items, key_n, key_c, color):
        if not items:
            return '<p class="empty-sm">No data</p>'
        mx = max(i[key_c] for i in items)
        return "".join(
            f'<div class="bar-row"><span class="bar-name">{i[key_n]}</span>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{round(i[key_c]/mx*100)}%;background:{color}"></div></div>'
            f'<span class="bar-cnt">{i[key_c]}</span></div>'
            for i in items
        )

    kpi_html = (
        kpi("Repos", curr.get("total", 0), prev.get("total", 0), "#38bdf8") +
        kpi("Avg score", curr.get("avg_score", 0), prev.get("avg_score", 0), "#4ade80") +
        kpi("XAI", curr.get("cat_split", {}).get("XAI", 0), prev.get("cat_split", {}).get("XAI", 0), "#a78bfa") +
        kpi("Trending", curr.get("cat_split", {}).get("Trending AI", 0), prev.get("cat_split", {}).get("Trending AI", 0), "#f472b6")
    )

    return f'''
<div class="weekly-layout">
  <aside class="weekly-sidebar">
    <p class="sidebar-label">Weeks</p>
    <div class="week-list" id="week-list">{sidebar}</div>
  </aside>
  <div class="weekly-main" id="weekly-main">
    <div class="kpi-row" id="kpi-row">{kpi_html}</div>
    <div class="weekly-body">
      <section class="analysis-section" id="analysis-section">
        <h2 class="section-title">Analysis</h2>
        <div class="analysis-prose" id="analysis-prose">{md_to_html(analysis)}</div>
      </section>
      <aside class="weekly-charts" id="weekly-charts">
        <div class="chart-card">
          <h3 class="chart-title">XAI Methods</h3>
          <div class="bar-list" id="xai-bars">{bars(curr.get("xai_methods",[]),"method","count","#38bdf8")}</div>
        </div>
        <div class="chart-card">
          <h3 class="chart-title">AI Domains</h3>
          <div class="bar-list" id="dom-bars">{bars(curr.get("domains",[]),"domain","count","#a78bfa")}</div>
        </div>
        <div class="chart-card">
          <h3 class="chart-title">Top Stars</h3>
          <div class="star-list" id="star-list">{_star_list_html(curr.get("top_stars",[]))}</div>
        </div>
      </aside>
    </div>
  </div>
</div>
<script>
const WEEKLY_DATA = {all_data};
function loadWeek(i) {{
  const d = WEEKLY_DATA[i]; if (!d) return;
  const curr = d.data.curr || {{}}, prev = d.data.prev || {{}};
  document.querySelectorAll('.week-btn').forEach((b,j) => b.classList.toggle('active', i===j));
  document.getElementById('analysis-prose').innerHTML = mdHtml(d.groq_analysis || '');
  renderKpi(curr, prev);
  renderBars('xai-bars', curr.xai_methods||[], 'method','count','#38bdf8');
  renderBars('dom-bars',  curr.domains||[],     'domain','count','#a78bfa');
  renderStars('star-list', curr.top_stars||[]);
}}
function renderKpi(c,p) {{
  const data = [
    ['Repos', c.total||0, p.total||0, '#38bdf8'],
    ['Avg score', c.avg_score||0, p.avg_score||0, '#4ade80'],
    ['XAI', (c.cat_split||{{}}).XAI||0, (p.cat_split||{{}}).XAI||0, '#a78bfa'],
    ['Trending', (c.cat_split||{{}})['Trending AI']||0, (p.cat_split||{{}})['Trending AI']||0, '#f472b6'],
  ];
  document.getElementById('kpi-row').innerHTML = data.map(([lbl,cv,pv,col]) => {{
    const d = cv-pv, cls = d>0?'up':d<0?'down':'flat', sign=d>0?'+':'';
    return `<div class="kpi-card"><div class="kpi-val" style="color:${{col}}">${{cv}}</div><div class="kpi-lbl">${{lbl}}</div><span class="kpi-delta ${{cls}}">${{sign}}${{d}}</span></div>`;
  }}).join('');
}}
function renderBars(id, items, kn, kc, color) {{
  if (!items.length) {{ document.getElementById(id).innerHTML='<p class="empty-sm">No data</p>'; return; }}
  const mx = Math.max(...items.map(i=>i[kc]));
  document.getElementById(id).innerHTML = items.map(i =>
    `<div class="bar-row"><span class="bar-name">${{i[kn]}}</span><div class="bar-track"><div class="bar-fill" style="width:${{Math.round(i[kc]/mx*100)}}%;background:${{color}}"></div></div><span class="bar-cnt">${{i[kc]}}</span></div>`
  ).join('');
}}
function renderStars(id, repos) {{
  document.getElementById(id).innerHTML = repos.map(r => {{
    const sf = r.stars>=1000?(r.stars/1000).toFixed(1)+'k':r.stars;
    return `<a class="star-item" href="${{r.url}}" target="_blank"><span class="star-name">${{r.name.split('/').pop()}}</span><span class="star-val">★ ${{sf}}</span></a>`;
  }}).join('');
}}
</script>'''

def _star_list_html(repos: list) -> str:
    return "".join(
        f'<a class="star-item" href="{r["url"]}" target="_blank">'
        f'<span class="star-name">{r["name"].split("/")[-1]}</span>'
        f'<span class="star-val">★ {star_fmt(r["stars"])}</span>'
        f'</a>'
        for r in repos
    )

# ── Insight tab ────────────────────────────────────────────────────────────────

def render_insight_tab(recs: list, arxiv: list) -> str:
    latest    = recs[0] if recs else {}
    data      = latest.get("data", {})
    top_repos = data.get("top_repos", [])
    pattern   = data.get("pattern") or {}
    analysis  = latest.get("groq_analysis", "")
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_KEY", "")

    def repo_card(r):
        sf  = star_fmt(r.get("stars", 0))
        sc  = score_color(r.get("score", 0))
        methods = "".join(f'<span class="tag">{m}</span>' for m in (r.get("methods") or [])[:3])
        return (
            f'<article class="feed-card" data-repo="{r["name"]}">'
            f'<div class="feed-head">'
            f'<div>'
            f'<a href="{r["url"]}" target="_blank" class="feed-name">{r["name"].split("/")[-1]}</a>'
            f'<span class="cat-badge {"xai" if r.get("cat")=="XAI" else "trend"}">{r.get("cat","")}</span>'
            f'</div>'
            f'<div class="feed-actions">'
            f'<button class="btn-like" onclick="setPref(\'{r["name"]}\',\'{r["url"]}\',true,this)">👍</button>'
            f'<button class="btn-dislike" onclick="setPref(\'{r["name"]}\',\'{r["url"]}\',false,this)">👎</button>'
            f'</div>'
            f'</div>'
            f'<p class="feed-problem">{r.get("problem","")}</p>'
            f'{"<div class=tags>" + methods + "</div>" if methods else ""}'
            f'<div class="feed-foot"><span class="stars">★ {sf}</span>'
            f'<span style="color:{sc};font-size:.72rem">score {r.get("score",0)}</span></div>'
            f'</article>'
        )

    def paper_card(p):
        authors = ", ".join((p.get("authors") or [])[:3])
        linked  = "".join(
            f'<span class="tag purple">{r.split("/")[-1]}</span>'
            for r in (p.get("linked_repos") or [])[:2]
        )
        return (
            f'<article class="paper-card">'
            f'<a href="{p["url"]}" target="_blank" class="paper-title">{p["title"]}</a>'
            f'<p class="paper-meta">{authors} · {p.get("published","")}</p>'
            f'<p class="paper-abstract">{p.get("abstract","")[:200]}…</p>'
            f'{"<div class=tags>" + linked + "</div>" if linked else ""}'
            f'</article>'
        )

    repos_html  = "".join(repo_card(r) for r in top_repos) or '<p class="empty">No data — run insight_engine.py first.</p>'
    papers_html = "".join(paper_card(p) for p in arxiv) or '<p class="empty">No papers — run arxiv_fetch.py first.</p>'
    pattern_summary = pattern.get("summary", "")

    return f'''
<div class="insight-layout">
  <div class="insight-main">
    <div class="insight-tabs">
      <button class="itab active" onclick="switchItab('feed',this)">🎯 Feed</button>
      <button class="itab" onclick="switchItab('papers',this)">📄 ArXiv</button>
      <button class="itab" onclick="switchItab('analysis',this)">🤖 Briefing</button>
    </div>
    {"<div class='pattern-bar'><span class='pattern-lbl'>Your profile:</span><span class='pattern-txt'>" + pattern_summary + "</span></div>" if pattern_summary else ""}
    <div class="itab-panel active" id="itab-feed"><div class="feed-grid">{repos_html}</div></div>
    <div class="itab-panel" id="itab-papers"><div class="papers-list">{papers_html}</div></div>
    <div class="itab-panel" id="itab-analysis"><div class="analysis-prose">{md_to_html(analysis)}</div></div>
  </div>
  <aside class="insight-sidebar">
    <p class="sidebar-label">Your preferences</p>
    <div id="pref-list"><p class="empty-sm">Like/dislike repos to build your profile.</p></div>
  </aside>
</div>
<script>
const SB_URL = "{supabase_url}";
const SB_KEY = "{supabase_key}";
function switchItab(name, btn) {{
  document.querySelectorAll('.itab').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('.itab-panel').forEach(p=>p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('itab-'+name).classList.add('active');
}}
async function setPref(repoName, repoUrl, liked, btn) {{
  const sibling = btn.parentNode.querySelector(liked?'.btn-dislike':'.btn-like');
  btn.classList.toggle('active'); sibling.classList.remove('active');
  const isActive = btn.classList.contains('active');
  await fetch(SB_URL+'/rest/v1/repo_preferences', {{
    method:'POST', headers:{{'apikey':SB_KEY,'Authorization':'Bearer '+SB_KEY,'Content-Type':'application/json','Prefer':'resolution=merge-duplicates'}},
    body: JSON.stringify({{repo_name:repoName, repo_url:repoUrl, liked: isActive ? liked : null}})
  }});
  loadPrefs();
}}
async function loadPrefs() {{
  try {{
    const r = await fetch(SB_URL+'/rest/v1/repo_preferences?select=*&order=created_at.desc&limit=20', {{headers:{{'apikey':SB_KEY,'Authorization':'Bearer '+SB_KEY}}}});
    const prefs = await r.json();
    prefs.forEach(p => {{
      const lb = document.querySelector(`[data-repo="${{p.repo_name}}"] .btn-like`);
      const db2 = document.querySelector(`[data-repo="${{p.repo_name}}"] .btn-dislike`);
      if(lb)  lb.classList.toggle('active', p.liked===true);
      if(db2) db2.classList.toggle('active', p.liked===false);
    }});
    const liked    = prefs.filter(p=>p.liked===true);
    const disliked = prefs.filter(p=>p.liked===false);
    document.getElementById('pref-list').innerHTML = [
      ...liked.map(p=>`<div class="pref-row"><span>${{p.repo_name.split('/').pop()}}</span><span class="badge-like">👍</span></div>`),
      ...disliked.map(p=>`<div class="pref-row"><span>${{p.repo_name.split('/').pop()}}</span><span class="badge-dislike">👎</span></div>`),
    ].join('') || '<p class="empty-sm">No preferences yet.</p>';
  }} catch(e) {{ console.error(e); }}
}}
loadPrefs();
</script>'''

# ── Shared JS md renderer for weekly tab ──────────────────────────────────────

MD_JS = """
function mdHtml(text) {
  if (!text) return '';
  return text
    .replace(/## (.*)/g, '<h2 class="md-h2">$1</h2>')
    .replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>')
    .replace(/\\[([^\\]]+)\\]\\(([^)]+)\\)/g, '<a href="$2" target="_blank">$1</a>')
    .replace(/^- (.*)/gm, '<li class="md-li">$1</li>')
    .replace(/(<li[^>]*>.*<\\/li>\\n?)+/g, m => '<ul class="md-ul">'+m+'</ul>')
    .replace(/\\n\\n/g, '</p><p class="md-p">')
    .replace(/^(?!<)/gm, '')
    .replace(/<p class="md-p"><\\/p>/g, '');
}
"""

# ── Build full HTML ────────────────────────────────────────────────────────────

def build_html(repos, trends, weekly, arxiv, recs) -> str:
    # Score and sort repos
    visible = []
    for r in repos:
        s = score_from_repo(r)
        if s > 0:
            r["_score"] = s
            visible.append(r)
    visible.sort(key=lambda r: r["_score"], reverse=True)

    total   = len(visible)
    xai_n   = sum(1 for r in visible if r.get("category") == "XAI")
    trend_n = total - xai_n
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    cards_html   = "\n".join(render_repo_card(r) for r in visible)
    weekly_html  = render_weekly_tab(weekly)
    insight_html = render_insight_tab(recs, arxiv)

    return f'''<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Hub</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Instrument+Serif:ital@0;1&family=Geist:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
/* ── Reset & tokens ─────────────────────────────────────── */
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#07090f;
  --surface:#0e1117;
  --surface2:#151a24;
  --border:#1d2535;
  --border2:#263044;
  --text:#dde3ef;
  --muted:#5a6480;
  --muted2:#3d4760;
  --blue:#4f9cf9;
  --purple:#9d72ff;
  --green:#36d97b;
  --amber:#f5a623;
  --pink:#f472b6;
  --teal:#2dd4bf;
  --red:#f87171;
  --radius:10px;
  --font-mono:'Space Mono',monospace;
  --font-serif:'Instrument Serif',serif;
  --font-sans:'Geist',sans-serif;
}}

body{{background:var(--bg);color:var(--text);font-family:var(--font-sans);font-size:15px;line-height:1.65;min-height:100vh}}
a{{color:var(--blue);text-decoration:none}}
a:hover{{text-decoration:underline}}
button{{font-family:var(--font-sans);cursor:pointer}}

/* ── App shell ──────────────────────────────────────────── */
.app{{display:flex;flex-direction:column;min-height:100vh}}

/* ── Nav ────────────────────────────────────────────────── */
.nav{{
  display:flex;align-items:center;gap:2rem;
  padding:.9rem 2rem;
  border-bottom:1px solid var(--border);
  background:var(--bg);
  position:sticky;top:0;z-index:100;
  backdrop-filter:blur(12px);
}}
.nav-brand{{
  font-family:var(--font-mono);font-size:.85rem;font-weight:700;
  color:var(--blue);letter-spacing:-.02em;white-space:nowrap;
}}
.nav-tabs{{display:flex;gap:0;margin-left:auto}}
.nav-tab{{
  background:none;border:none;border-bottom:2px solid transparent;
  color:var(--muted);padding:.5rem 1.1rem;font-size:.8rem;
  letter-spacing:.05em;text-transform:uppercase;
  transition:all .2s;margin-bottom:-1px;
}}
.nav-tab:hover{{color:var(--text)}}
.nav-tab.active{{color:var(--blue);border-bottom-color:var(--blue)}}
.nav-meta{{font-size:.7rem;color:var(--muted2);font-family:var(--font-mono);white-space:nowrap}}

/* ── Stats pills ────────────────────────────────────────── */
.stats-bar{{
  display:flex;gap:.6rem;padding:.8rem 2rem;
  border-bottom:1px solid var(--border);background:var(--surface);
  flex-wrap:wrap;
}}
.stat-pill{{
  font-size:.72rem;color:var(--muted);
  background:var(--surface2);border:1px solid var(--border);
  border-radius:99px;padding:.2rem .8rem;
}}
.stat-pill b{{color:var(--text)}}

/* ── Tab panels ─────────────────────────────────────────── */
.tab-panel{{display:none;padding:1.5rem 2rem;flex:1}}
.tab-panel.active{{display:block}}

/* ── Repos: filter bar ──────────────────────────────────── */
.filter-bar{{display:flex;gap:.5rem;margin-bottom:1.5rem;flex-wrap:wrap}}
.filter-btn{{
  background:var(--surface2);border:1px solid var(--border);color:var(--muted);
  border-radius:8px;padding:.3rem .85rem;font-size:.75rem;
  transition:all .2s;
}}
.filter-btn:hover,.filter-btn.active{{
  background:#4f9cf918;border-color:var(--blue);color:var(--blue);
}}

/* ── Card grid ──────────────────────────────────────────── */
.card-grid{{
  display:grid;
  grid-template-columns:repeat(auto-fill,minmax(290px,1fr));
  gap:1rem;
}}

/* ── Repo card ──────────────────────────────────────────── */
.card{{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius);padding:1.1rem;
  cursor:pointer;transition:border-color .2s,transform .15s,box-shadow .2s;
  position:relative;overflow:hidden;
}}
.card::after{{
  content:'';position:absolute;inset:0;top:0;height:2px;
  background:linear-gradient(90deg,var(--blue),var(--purple));
  opacity:0;transition:opacity .2s;
}}
.card:hover{{border-color:var(--border2);transform:translateY(-2px);box-shadow:0 16px 48px #00000050}}
.card:hover::after{{opacity:1}}

.card-head{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:.8rem}}
.card-badges{{display:flex;gap:.35rem;flex-wrap:wrap;align-items:center}}
.cat-badge{{
  font-size:.62rem;font-weight:600;padding:.15rem .5rem;border-radius:5px;
  text-transform:uppercase;letter-spacing:.04em;
}}
.cat-badge.xai{{background:#0a3d6b;color:#60a5fa}}
.cat-badge.trend{{background:#2d1d5a;color:#a78bfa}}
.domain-badge{{font-size:.62rem;padding:.15rem .5rem;border-radius:5px}}

.score-chip{{
  display:flex;align-items:center;justify-content:center;
  width:38px;height:38px;border-radius:8px;
  border:1.5px solid var(--sc,#4ade80);
  color:var(--sc,#4ade80);
  font-family:var(--font-mono);font-size:.95rem;font-weight:700;
  box-shadow:0 0 16px color-mix(in srgb,var(--sc,#4ade80) 25%,transparent);
  flex-shrink:0;
}}

.card-title{{
  font-family:var(--font-sans);font-size:.95rem;font-weight:600;
  color:#f0f4ff;margin-bottom:.1rem;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
}}
.card-owner{{font-size:.68rem;color:var(--muted2);margin-bottom:.55rem}}
.card-problem{{
  font-size:.78rem;color:#8a95b0;line-height:1.5;margin-bottom:.45rem;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
}}
.card-innov{{
  font-size:.73rem;color:var(--muted);line-height:1.4;margin-bottom:.35rem;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
}}
.pills{{display:flex;gap:.3rem;flex-wrap:wrap;margin:.45rem 0}}
.pill{{
  font-size:.6rem;padding:.1rem .4rem;border-radius:4px;
  background:var(--surface2);border:1px solid var(--border2);color:var(--muted);
}}
.tags{{display:flex;gap:.3rem;flex-wrap:wrap;margin-bottom:.6rem}}
.tag{{font-size:.6rem;padding:.1rem .4rem;background:#0b2244;color:#60a5fa;border-radius:4px}}
.tag.purple{{background:#1e0d44;color:#a78bfa}}
.card-foot{{
  display:flex;justify-content:space-between;align-items:center;
  border-top:1px solid var(--border);padding-top:.55rem;
  font-size:.7rem;
}}
.stars{{color:var(--amber)}}
.rel{{color:var(--muted)}}

/* ── Weekly layout ──────────────────────────────────────── */
.weekly-layout{{display:grid;grid-template-columns:180px 1fr;gap:1.5rem;min-height:60vh}}
.weekly-sidebar{{padding-top:.5rem}}
.sidebar-label{{font-size:.65rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted2);margin-bottom:.75rem}}
.week-list{{display:flex;flex-direction:column;gap:.3rem}}
.week-btn{{
  background:none;border:1px solid var(--border);color:var(--muted);
  border-radius:7px;padding:.35rem .7rem;font-size:.75rem;
  text-align:left;transition:all .2s;
}}
.week-btn:hover{{background:var(--surface2);color:var(--text)}}
.week-btn.active{{background:#4f9cf918;border-color:var(--blue);color:var(--blue)}}

.weekly-main{{min-width:0}}
.kpi-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:.75rem;margin-bottom:1.5rem}}
.kpi-card{{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius);padding:1rem;text-align:center;
}}
.kpi-val{{font-family:var(--font-mono);font-size:1.6rem;font-weight:700;line-height:1}}
.kpi-lbl{{font-size:.68rem;color:var(--muted);margin-top:.3rem}}
.kpi-delta{{font-size:.7rem;font-weight:600;display:block;margin-top:.25rem}}
.kpi-delta.up{{color:var(--green)}}.kpi-delta.down{{color:var(--red)}}.kpi-delta.flat{{color:var(--muted)}}

.weekly-body{{display:grid;grid-template-columns:1fr 280px;gap:1.2rem;align-items:start}}
.analysis-section{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:1.5rem}}
.section-title{{font-family:var(--font-serif);font-size:1.1rem;font-style:italic;color:var(--text);margin-bottom:1rem;padding-bottom:.75rem;border-bottom:1px solid var(--border)}}
.weekly-charts{{display:flex;flex-direction:column;gap:.8rem}}
.chart-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:1rem}}
.chart-title{{font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:.8rem}}

.bar-list{{display:flex;flex-direction:column;gap:.5rem}}
.bar-row{{display:flex;align-items:center;gap:.5rem}}
.bar-name{{font-size:.72rem;color:var(--text);min-width:72px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.bar-track{{flex:1;background:var(--surface2);border-radius:99px;height:5px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:99px;transition:width .5s ease}}
.bar-cnt{{font-size:.68rem;color:var(--muted);min-width:20px;text-align:right}}

.star-list{{display:flex;flex-direction:column;gap:.4rem}}
.star-item{{display:flex;justify-content:space-between;align-items:center;padding:.4rem .5rem;background:var(--surface2);border-radius:6px;color:var(--text);font-size:.78rem}}
.star-item:hover{{background:var(--border)}}
.star-name{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:140px}}
.star-val{{color:var(--amber);flex-shrink:0;font-size:.75rem}}

/* ── Markdown prose ─────────────────────────────────────── */
.analysis-prose .md-h2{{font-family:var(--font-serif);font-style:italic;font-size:1.05rem;color:var(--text);margin:1.2rem 0 .5rem;padding-bottom:.4rem;border-bottom:1px solid var(--border)}}
.analysis-prose .md-h2:first-child{{margin-top:0}}
.analysis-prose .md-p{{font-size:.88rem;color:#8a95b0;line-height:1.75;margin-bottom:.7rem}}
.analysis-prose .md-ul{{padding-left:1.2rem;margin-bottom:.7rem}}
.analysis-prose .md-li{{font-size:.88rem;color:#8a95b0;line-height:1.65;margin-bottom:.2rem}}
.analysis-prose strong{{color:var(--text)}}
.analysis-prose a{{color:var(--blue)}}

/* ── Insight layout ─────────────────────────────────────── */
.insight-layout{{display:grid;grid-template-columns:1fr 220px;gap:1.5rem}}
.insight-main{{min-width:0}}
.insight-tabs{{display:flex;gap:.4rem;margin-bottom:1.2rem}}
.itab{{
  background:var(--surface2);border:1px solid var(--border);color:var(--muted);
  border-radius:8px;padding:.3rem .8rem;font-size:.78rem;transition:all .2s;
}}
.itab:hover{{color:var(--text)}}
.itab.active{{background:#4f9cf918;border-color:var(--blue);color:var(--blue)}}
.itab-panel{{display:none}}.itab-panel.active{{display:block}}

.pattern-bar{{
  background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--purple);
  border-radius:var(--radius);padding:.7rem 1rem;margin-bottom:1rem;
  display:flex;gap:.8rem;align-items:center;flex-wrap:wrap;
}}
.pattern-lbl{{font-size:.68rem;color:var(--muted);white-space:nowrap}}
.pattern-txt{{font-size:.8rem;color:var(--text);flex:1}}

.feed-grid{{display:flex;flex-direction:column;gap:.75rem}}
.feed-card{{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius);padding:1rem;transition:border-color .2s;
}}
.feed-card:hover{{border-color:var(--border2)}}
.feed-head{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:.5rem;gap:.5rem}}
.feed-name{{font-weight:600;font-size:.88rem;color:var(--text)}}
.feed-name:hover{{color:var(--blue)}}
.feed-problem{{font-size:.78rem;color:#8a95b0;margin:.4rem 0}}
.feed-foot{{display:flex;justify-content:space-between;align-items:center;margin-top:.5rem}}
.feed-actions{{display:flex;gap:.35rem;flex-shrink:0}}
.btn-like,.btn-dislike{{
  background:none;border:1px solid var(--border);border-radius:6px;
  padding:.2rem .55rem;font-size:.72rem;transition:all .2s;
}}
.btn-like{{color:var(--green)}}
.btn-like:hover,.btn-like.active{{background:#0d4429;border-color:var(--green)}}
.btn-dislike{{color:var(--red)}}
.btn-dislike:hover,.btn-dislike.active{{background:#3d1a1a;border-color:var(--red)}}

.papers-list{{display:flex;flex-direction:column;gap:.75rem}}
.paper-card{{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius);padding:1rem;
}}
.paper-title{{font-weight:600;font-size:.85rem;color:var(--text);display:block;margin-bottom:.3rem;line-height:1.4}}
.paper-title:hover{{color:var(--blue)}}
.paper-meta{{font-size:.7rem;color:var(--muted);margin-bottom:.4rem}}
.paper-abstract{{font-size:.78rem;color:#8a95b0;line-height:1.5}}

.insight-sidebar{{padding-top:3.2rem}}
.pref-row{{display:flex;justify-content:space-between;align-items:center;padding:.4rem 0;border-bottom:1px solid var(--border);font-size:.78rem;color:var(--text)}}
.badge-like{{color:var(--green)}} .badge-dislike{{color:var(--red)}}

/* ── Empty states ───────────────────────────────────────── */
.empty{{color:var(--muted);font-size:.85rem;padding:2rem;text-align:center}}
.empty-sm{{color:var(--muted);font-size:.75rem;font-style:italic}}

/* ── Responsive ─────────────────────────────────────────── */
@media(max-width:900px){{
  .weekly-layout,.weekly-body{{grid-template-columns:1fr}}
  .weekly-sidebar{{display:flex;gap:.4rem;flex-wrap:wrap}}
  .kpi-row{{grid-template-columns:repeat(2,1fr)}}
}}
@media(max-width:680px){{
  body{{font-size:14px}}
  .nav{{padding:.75rem 1rem;gap:1rem}}
  .nav-meta{{display:none}}
  .tab-panel{{padding:1rem}}
  .insight-layout{{grid-template-columns:1fr}}
  .insight-sidebar{{display:none}}
  .stats-bar{{padding:.6rem 1rem}}
}}
</style>
</head>
<body>
<div class="app">

<!-- Nav -->
<nav class="nav">
  <span class="nav-brand">⬡ AI Hub</span>
  <div class="nav-tabs">
    <button class="nav-tab active" onclick="switchTab('repos',this)">Repos</button>
    <button class="nav-tab" onclick="switchTab('weekly',this)">Weekly</button>
    <button class="nav-tab" onclick="switchTab('insight',this)">Insight</button>
  </div>
  <span class="nav-meta">{updated}</span>
</nav>

<!-- Stats -->
<div class="stats-bar">
  <span class="stat-pill">📦 Total <b>{total}</b></span>
  <span class="stat-pill">🔍 XAI <b>{xai_n}</b></span>
  <span class="stat-pill">🔥 Trending <b>{trend_n}</b></span>
</div>

<!-- Tab: Repos -->
<div class="tab-panel active" id="tab-repos">
  <div class="filter-bar">
    <button class="filter-btn active" onclick="filterCards('all',this)">All</button>
    <button class="filter-btn" onclick="filterCards('XAI',this)">XAI</button>
    <button class="filter-btn" onclick="filterCards('Trending AI',this)">Trending</button>
    <button class="filter-btn" onclick="filterCards('high',this)">Score ≥ 70</button>
  </div>
  <div class="card-grid" id="card-grid">{cards_html}</div>
</div>

<!-- Tab: Weekly -->
<div class="tab-panel" id="tab-weekly">{weekly_html}</div>

<!-- Tab: Insight -->
<div class="tab-panel" id="tab-insight">{insight_html}</div>

</div>
<script>
{MD_JS}

function switchTab(name, btn) {{
  document.querySelectorAll('.nav-tab').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-'+name).classList.add('active');
}}

function filterCards(type, btn) {{
  document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.card').forEach(c=>{{
    const cat=c.dataset.cat, score=parseFloat(c.dataset.score||0);
    let show = type==='all' || (type==='XAI'&&cat==='XAI') ||
      (type==='Trending AI'&&cat==='Trending AI') || (type==='high'&&score>=70);
    c.style.display = show ? '' : 'none';
  }});
}}
</script>
</body>
</html>'''

# ── Entry point ────────────────────────────────────────────────────────────────

def export_all() -> None:
    db = get_client()
    print("📡 Fetching all data from Supabase…")
    repos, trends, weekly, arxiv, recs = fetch_all(db)
    print(f"  repos: {len(repos)} | trends: {len(trends)} weeks | "
          f"weekly: {len(weekly)} | arxiv: {len(arxiv)} | recs: {len(recs)}")

    html = build_html(repos, trends, weekly, arxiv, recs)

    os.makedirs("output", exist_ok=True)
    path = "output/index.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"🎉 Dashboard exported → {path}")


if __name__ == "__main__":
    export_all()
