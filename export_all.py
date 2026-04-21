"""
export_all.py — Export a single index.html with all 3 dashboards.

Tabs:
  1. Repos     — searchable card grid, full data, composite score
  2. Weekly    — editorial report with bar charts, readable prose
  3. Insight   — personal feed, ArXiv papers, like/dislike
"""
import os
import json
import math
from collections import Counter
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

def star_fmt(n):
    if n >= 1000: return f"{n/1000:.1f}k"
    return str(n)

DOMAIN_MAP = {
    "GenAI":      ("#e879f9", "🔮"),
    "NLP":        ("#60a5fa", "💬"),
    "CV":         ("#34d399", "👁"),
    "Multimodal": ("#a78bfa", "🌐"),
    "RL":         ("#fbbf24", "🎮"),
    "Audio":      ("#fb923c", "🎵"),
    "Other":      ("#94a3b8", "⚙"),
}

def domain_color(d): return DOMAIN_MAP.get(d, ("#94a3b8", "⚙"))[0]
def domain_icon(d):  return DOMAIN_MAP.get(d, ("#94a3b8", "⚙"))[1]

def esc(s):
    return str(s).replace("'", "&#39;").replace('"', "&quot;") if s else ""

# ── Repo card ──────────────────────────────────────────────────────────────────

def render_repo_card(repo):
    a = repo.get("analysis_result") or {}
    if a.get("skipped"):
        return ""

    name     = repo.get("repo_name", "")
    url      = repo.get("repo_url", "#")
    stars    = repo.get("stars", 0) or 0
    cat      = repo.get("category", "")
    score    = repo.get("_score", 0)
    rel      = a.get("relevance_score", "?")
    problem  = a.get("core_problem", "")
    domain   = a.get("ai_domain", "")
    methods  = a.get("xai_methods") or []
    stack    = a.get("tech_stack") or []
    innov    = a.get("key_innovation") or a.get("novelty") or ""
    why      = a.get("why_trending", "")
    scope    = a.get("scope", "")
    agnostic = a.get("model_agnostic")
    real     = a.get("real_world_applicable")
    topics   = repo.get("topics") or []

    sc  = score_color(score)
    dc  = domain_color(domain)
    di  = domain_icon(domain)
    cat_cls = "xai" if cat == "XAI" else "trend"
    short   = name.split("/")[-1]
    owner   = name.split("/")[0]

    all_tags   = list(dict.fromkeys(methods + stack))[:6]
    tags_html  = "".join(f'<span class="tag">{t}</span>' for t in all_tags)
    topic_html = "".join(f'<span class="topic">{t}</span>' for t in topics[:4])

    attrs = []
    if scope:            attrs.append(scope)
    if agnostic is True: attrs.append("model-agnostic")
    if real is True:     attrs.append("real-world")
    attr_html = "".join(f'<span class="attr">{a}</span>' for a in attrs)

    rel_pct = int(rel) * 10 if isinstance(rel, int) else 0

    return (
        f'<article class="card" data-cat="{cat}" data-score="{score}" data-domain="{esc(domain)}"'
        f' data-search="{esc((name+" "+problem+" "+domain+" "+" ".join(all_tags)).lower())}">'
        f'<div class="card-accent" style="background:linear-gradient(90deg,{sc}44,transparent)"></div>'
        f'<header class="card-head">'
        f'<div class="card-left">'
        f'<span class="cat-badge {cat_cls}">{cat}</span>'
        f'{f"<span class=domain-badge style=color:{dc}>{di} {domain}</span>" if domain else ""}'
        f'</div>'
        f'<div class="score-chip" style="border-color:{sc};color:{sc}">{score}</div>'
        f'</header>'
        f'<h3 class="card-title"><a href="{url}" target="_blank" rel="noopener">{short}</a></h3>'
        f'<p class="card-owner">{owner}/</p>'
        f'<p class="card-problem">{problem}</p>'
        f'{f"<p class=card-innov>💡 {innov}</p>" if innov else ""}'
        f'{f"<p class=card-why>🔥 {why}</p>"     if why   else ""}'
        f'{f"<div class=attr-row>{attr_html}</div>" if attrs else ""}'
        f'{f"<div class=tag-row>{tags_html}</div>"   if all_tags else ""}'
        f'{f"<div class=topic-row>{topic_html}</div>" if topics else ""}'
        f'<footer class="card-foot">'
        f'<span class="stars">★ {star_fmt(stars)}</span>'
        f'<div class="rel-bar">'
        f'<span class="rel-lbl">rel</span>'
        f'<div class="rel-track"><div class="rel-fill" style="width:{rel_pct}%;background:{sc}"></div></div>'
        f'<span class="rel-val">{rel}/10</span>'
        f'</div>'
        f'</footer>'
        f'</article>'
    )

# ── Weekly helpers ─────────────────────────────────────────────────────────────

def _bars_html(items, key_n, key_c, color):
    if not items:
        return '<p class="empty-sm">No data</p>'
    mx = max(i[key_c] for i in items)
    return "".join(
        f'<div class="bar-row">'
        f'<span class="bar-name">{i[key_n]}</span>'
        f'<div class="bar-track"><div class="bar-fill" style="width:{round(i[key_c]/mx*100)}%;background:{color}"></div></div>'
        f'<span class="bar-cnt">{i[key_c]}</span>'
        f'</div>'
        for i in items
    )

def _top_repos_html(repos):
    if not repos:
        return '<p class="empty-sm">No data</p>'
    return "".join(
        f'<a class="top-repo-row" href="{r["url"]}" target="_blank">'
        f'<span class="top-repo-rank">#{i+1}</span>'
        f'<span class="top-repo-name">{r["name"].split("/")[-1]}</span>'
        f'<span class="top-repo-meta">'
        f'<span class="top-repo-cat {"xai" if r.get("cat")=="XAI" else "trend"}">{r.get("cat","")}</span>'
        f'<span class="top-repo-stars">★ {star_fmt(r["stars"])}</span>'
        f'</span>'
        f'</a>'
        for i, r in enumerate(repos[:5])
    )

def render_weekly_tab(weekly):
    if not weekly:
        return '<p class="empty">No weekly reports yet.</p>'

    latest   = weekly[0]
    data     = latest.get("data", {})
    curr     = data.get("curr", {})
    prev     = data.get("prev", {})
    analysis = latest.get("groq_analysis", "")

    sidebar = "".join(
        f'<button class="week-btn {"active" if i==0 else ""}" onclick="loadWeek({i})">'
        f'{r["week_label"]}</button>'
        for i, r in enumerate(weekly)
    )
    all_data_json = json.dumps(
        [{"week_label": r["week_label"], "data": r.get("data", {}),
          "groq_analysis": r.get("groq_analysis", "")} for r in weekly],
        ensure_ascii=False,
    )

    def kpi(icon, label, cv, pv, color):
        delta = cv - pv if isinstance(cv, (int, float)) and isinstance(pv, (int, float)) else None
        d_html = ""
        if delta is not None:
            cls  = "up" if delta > 0 else ("dn" if delta < 0 else "flat")
            sign = "+" if delta > 0 else ""
            d_html = f'<span class="kpi-delta {cls}">{sign}{delta}</span>'
        return (
            f'<div class="kpi-card">'
            f'<div class="kpi-icon">{icon}</div>'
            f'<div class="kpi-val" style="color:{color}">{cv}</div>'
            f'<div class="kpi-lbl">{label}</div>'
            f'{d_html}'
            f'</div>'
        )

    kpi_html = (
        kpi("📦", "Total repos",   curr.get("total", 0),     prev.get("total", 0),     "#38bdf8") +
        kpi("📊", "Avg relevance", curr.get("avg_score", 0), prev.get("avg_score", 0), "#4ade80") +
        kpi("🔍", "XAI",           curr.get("cat_split", {}).get("XAI", 0),          prev.get("cat_split", {}).get("XAI", 0),          "#a78bfa") +
        kpi("🔥", "Trending AI",   curr.get("cat_split", {}).get("Trending AI", 0),  prev.get("cat_split", {}).get("Trending AI", 0),  "#f472b6")
    )

    return (
        f'<div class="weekly-wrap">'
        f'<div class="weekly-sidebar">'
        f'<p class="sidebar-lbl">History</p>'
        f'<div id="week-list">{sidebar}</div>'
        f'</div>'
        f'<div class="weekly-main">'
        f'<div class="kpi-row" id="kpi-row">{kpi_html}</div>'
        f'<div class="weekly-body">'
        f'<div class="analysis-col">'
        f'<div class="analysis-card"><div class="analysis-prose" id="analysis-prose">{md_to_html(analysis)}</div></div>'
        f'</div>'
        f'<div class="charts-col">'
        f'<div class="chart-card"><div class="chart-title">🔬 XAI Methods</div><div id="xai-bars">{_bars_html(curr.get("xai_methods",[]),"method","count","#38bdf8")}</div></div>'
        f'<div class="chart-card"><div class="chart-title">🌐 AI Domains</div><div id="dom-bars">{_bars_html(curr.get("domains",[]),"domain","count","#a78bfa")}</div></div>'
        f'<div class="chart-card"><div class="chart-title">⭐ Top by Stars</div><div id="star-list">{_top_repos_html(curr.get("top_stars",[]))}</div></div>'
        f'<div class="chart-card"><div class="chart-title">🏆 Top by Score</div><div id="score-list">{_top_repos_html(curr.get("top_repos",[]))}</div></div>'
        f'</div>'
        f'</div>'
        f'</div>'
        f'</div>'
        f'<script>'
        f'const WEEKLY_DATA={all_data_json};'
        f'function loadWeek(i){{'
        f'const d=WEEKLY_DATA[i];if(!d)return;'
        f'const curr=d.data.curr||{{}},prev=d.data.prev||{{}};'
        f'document.querySelectorAll(".week-btn").forEach((b,j)=>b.classList.toggle("active",i===j));'
        f'document.getElementById("analysis-prose").innerHTML=mdHtml(d.groq_analysis||"");'
        f'renderKpi(curr,prev);'
        f'renderBars("xai-bars",curr.xai_methods||[],"method","count","#38bdf8");'
        f'renderBars("dom-bars",curr.domains||[],"domain","count","#a78bfa");'
        f'renderTopRepos("star-list",curr.top_stars||[]);'
        f'renderTopRepos("score-list",curr.top_repos||[]);'
        f'}}'
        f'function renderKpi(c,p){{'
        f'const items=[["📦","Total repos",c.total||0,p.total||0,"#38bdf8"],'
        f'["📊","Avg relevance",c.avg_score||0,p.avg_score||0,"#4ade80"],'
        f'["🔍","XAI",(c.cat_split||{{}}).XAI||0,(p.cat_split||{{}}).XAI||0,"#a78bfa"],'
        f'["🔥","Trending AI",(c.cat_split||{{}})["Trending AI"]||0,(p.cat_split||{{}})["Trending AI"]||0,"#f472b6"]];'
        f'document.getElementById("kpi-row").innerHTML=items.map(([ic,lbl,cv,pv,col])=>{{'
        f'const d=cv-pv,cls=d>0?"up":d<0?"dn":"flat",sign=d>0?"+":"";'
        f'return `<div class="kpi-card"><div class="kpi-icon">${{ic}}</div><div class="kpi-val" style="color:${{col}}">${{cv}}</div><div class="kpi-lbl">${{lbl}}</div><span class="kpi-delta ${{cls}}">${{sign}}${{d}}</span></div>`;'
        f'}}).join("");'
        f'}}'
        f'function renderBars(id,items,kn,kc,color){{'
        f'if(!items.length){{document.getElementById(id).innerHTML=\'<p class="empty-sm">No data</p>\';return;}}'
        f'const mx=Math.max(...items.map(i=>i[kc]));'
        f'document.getElementById(id).innerHTML=items.map(i=>'
        f'`<div class="bar-row"><span class="bar-name">${{i[kn]}}</span><div class="bar-track"><div class="bar-fill" style="width:${{Math.round(i[kc]/mx*100)}}%;background:${{color}}"></div></div><span class="bar-cnt">${{i[kc]}}</span></div>`'
        f').join("");'
        f'}}'
        f'function renderTopRepos(id,repos){{'
        f'document.getElementById(id).innerHTML=repos.map((r,i)=>'
        f'`<a class="top-repo-row" href="${{r.url}}" target="_blank"><span class="top-repo-rank">#${{i+1}}</span><span class="top-repo-name">${{r.name.split("/").pop()}}</span><span class="top-repo-meta"><span class="top-repo-cat ${{r.cat==="XAI"?"xai":"trend"}}">${{r.cat}}</span><span class="top-repo-stars">★ ${{r.stars>=1000?(r.stars/1000).toFixed(1)+"k":r.stars}}</span></span></a>`'
        f').join("");'
        f'}}'
        f'</script>'
    )

# ── Insight tab ────────────────────────────────────────────────────────────────

def render_insight_tab(recs, arxiv):
    latest     = recs[0] if recs else {}
    data       = latest.get("data", {})
    top_repos  = data.get("top_repos", [])
    pattern    = data.get("pattern") or {}
    liked_n    = data.get("liked_count", 0)
    disliked_n = data.get("disliked_count", 0)
    analysis   = latest.get("groq_analysis", "")
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_KEY", "")

    def feed_card(r):
        # Clamp score to 100 for display (personalisation bonus can push beyond)
        raw_score   = r.get("score", 0)
        disp_score  = min(raw_score, 100)
        sc  = score_color(disp_score)
        dc  = domain_color(r.get("domain", ""))
        di  = domain_icon(r.get("domain", ""))
        sf  = star_fmt(r.get("stars", 0))
        methods_html = "".join(f'<span class="tag">{m}</span>' for m in (r.get("methods") or [])[:3])
        return (
            f'<article class="feed-card" data-repo="{esc(r["name"])}">'
            f'<div class="feed-head">'
            f'<div class="feed-title-row">'
            f'<a href="{r["url"]}" target="_blank" class="feed-name">{r["name"].split("/")[-1]}</a>'
            f'<span class="cat-badge {"xai" if r.get("cat")=="XAI" else "trend"}">{r.get("cat","")}</span>'
            f'</div>'
            f'<div class="feed-actions">'
            f'<button class="btn-like" title="Like" onclick="setPref(\'{esc(r["name"])}\',\'{esc(r["url"])}\',true,this)">👍</button>'
            f'<button class="btn-dislike" title="Dislike" onclick="setPref(\'{esc(r["name"])}\',\'{esc(r["url"])}\',false,this)">👎</button>'
            f'</div>'
            f'</div>'
            f'{f"<p class=feed-domain style=color:{dc}>{di} {r.get(chr(100)+chr(111)+chr(109)+chr(97)+chr(105)+chr(110),chr(32))}</p>" if r.get("domain") else ""}'
            f'<p class="feed-problem">{r.get("problem","")}</p>'
            f'{f"<div class=tag-row>{methods_html}</div>" if methods_html else ""}'
            f'<div class="feed-foot">'
            f'<span class="stars">★ {sf}</span>'
            f'<div class="score-meter"><div class="score-meter-fill" style="width:{disp_score}%;background:{sc}"></div></div>'
            f'<span class="score-val" style="color:{sc}">{disp_score}</span>'
            f'</div>'
            f'</article>'
        )

    def paper_card(p):
        authors = ", ".join((p.get("authors") or [])[:3])
        if len(p.get("authors") or []) > 3:
            authors += " et al."
        linked      = p.get("linked_repos") or []
        linked_html = "".join(f'<span class="tag purple">{r.split("/")[-1]}</span>' for r in linked[:2])
        abstract    = (p.get("abstract") or "")[:220]
        return (
            f'<article class="paper-card">'
            f'<div class="paper-date">{p.get("published","")}</div>'
            f'<a href="{p["url"]}" target="_blank" class="paper-title">{p["title"]}</a>'
            f'<p class="paper-authors">{authors}</p>'
            f'<p class="paper-abstract">{abstract}…</p>'
            f'{f"<div class=tag-row>🔗 {linked_html}</div>" if linked_html else ""}'
            f'</article>'
        )

    pref_summary  = pattern.get("summary", "")
    pref_domains  = pattern.get("preferred_domains") or []
    pref_methods  = pattern.get("preferred_methods") or []

    pref_bar = ""
    if pref_summary:
        dom_tags  = "".join(f'<span class="tag">{d}</span>' for d in pref_domains[:4])
        meth_tags = "".join(f'<span class="tag">{m}</span>' for m in pref_methods[:4])
        pref_bar = (
            f'<div class="pref-banner">'
            f'<div class="pref-banner-icon">🎯</div>'
            f'<div class="pref-banner-body">'
            f'<p class="pref-summary">{pref_summary}</p>'
            f'{f"<div class=tag-row>{dom_tags}{meth_tags}</div>" if dom_tags or meth_tags else ""}'
            f'</div>'
            f'<div class="pref-stats"><span>👍 {liked_n}</span><span>👎 {disliked_n}</span></div>'
            f'</div>'
        )

    feed_html   = "".join(feed_card(r) for r in top_repos) or '<p class="empty">No data — run insight_engine.py first.</p>'
    papers_html = "".join(paper_card(p) for p in arxiv)    or '<p class="empty">No papers — run arxiv_fetch.py first.</p>'

    return (
        f'<div class="insight-wrap">'
        f'<div class="insight-main">'
        f'{pref_bar}'
        f'<div class="insight-tabs">'
        f'<button class="itab active" onclick="switchItab(\'feed\',this)">🎯 Personal Feed</button>'
        f'<button class="itab" onclick="switchItab(\'papers\',this)">📄 ArXiv ({len(arxiv)})</button>'
        f'<button class="itab" onclick="switchItab(\'analysis\',this)">🤖 Weekly Briefing</button>'
        f'</div>'
        f'<div class="itab-panel active" id="itab-feed"><div class="feed-grid">{feed_html}</div></div>'
        f'<div class="itab-panel" id="itab-papers"><div class="papers-list">{papers_html}</div></div>'
        f'<div class="itab-panel" id="itab-analysis"><div class="analysis-card"><div class="analysis-prose">{md_to_html(analysis)}</div></div></div>'
        f'</div>'
        f'<aside class="insight-sidebar">'
        f'<div class="sidebar-section">'
        f'<p class="sidebar-lbl">Your likes</p>'
        f'<div id="liked-list"><p class="empty-sm">No likes yet.</p></div>'
        f'</div>'
        f'<div class="sidebar-section">'
        f'<p class="sidebar-lbl">Your dislikes</p>'
        f'<div id="disliked-list"><p class="empty-sm">No dislikes yet.</p></div>'
        f'</div>'
        f'</aside>'
        f'</div>'
        f'<script>'
        f'const SB_URL="{supabase_url}",SB_KEY="{supabase_key}";'
        f'function switchItab(name,btn){{'
        f'document.querySelectorAll(".itab").forEach(b=>b.classList.remove("active"));'
        f'document.querySelectorAll(".itab-panel").forEach(p=>p.classList.remove("active"));'
        f'btn.classList.add("active");document.getElementById("itab-"+name).classList.add("active");'
        f'}}'
        f'async function setPref(name,url,liked,btn){{'
        f'const sib=btn.parentNode.querySelector(liked?".btn-dislike":".btn-like");'
        f'btn.classList.toggle("active");sib.classList.remove("active");'
        f'const isActive=btn.classList.contains("active");'
        f'try{{'
        f'await fetch(SB_URL+"/rest/v1/repo_preferences",{{'
        f'method:"POST",'
        f'headers:{{"apikey":SB_KEY,"Authorization":"Bearer "+SB_KEY,"Content-Type":"application/json","Prefer":"resolution=merge-duplicates"}},'
        f'body:JSON.stringify({{repo_name:name,repo_url:url,liked:isActive?liked:null}})'
        f'}});loadPrefs();'
        f'}}catch(e){{console.error(e);}}'
        f'}}'
        f'async function loadPrefs(){{'
        f'if(!SB_URL||!SB_KEY)return;'
        f'try{{'
        f'const r=await fetch(SB_URL+"/rest/v1/repo_preferences?select=*&order=created_at.desc&limit=30",'
        f'{{headers:{{"apikey":SB_KEY,"Authorization":"Bearer "+SB_KEY}}}});'
        f'const prefs=await r.json();'
        f'prefs.forEach(p=>{{'
        f'const lb=document.querySelector(`[data-repo="${{p.repo_name}}"] .btn-like`);'
        f'const db=document.querySelector(`[data-repo="${{p.repo_name}}"] .btn-dislike`);'
        f'if(lb)lb.classList.toggle("active",p.liked===true);'
        f'if(db)db.classList.toggle("active",p.liked===false);'
        f'}});'
        f'const liked=prefs.filter(p=>p.liked===true);'
        f'const disliked=prefs.filter(p=>p.liked===false);'
        f'document.getElementById("liked-list").innerHTML='
        f'liked.map(p=>`<div class="pref-row pref-like">${{p.repo_name.split("/").pop()}}</div>`).join("")'
        f'||\'<p class="empty-sm">No likes yet.</p>\';'
        f'document.getElementById("disliked-list").innerHTML='
        f'disliked.map(p=>`<div class="pref-row pref-dislike">${{p.repo_name.split("/").pop()}}</div>`).join("")'
        f'||\'<p class="empty-sm">No dislikes yet.</p>\';'
        f'}}catch(e){{console.error(e);}}'
        f'}}'
        f'loadPrefs();'
        f'</script>'
    )

# ── MD JS helper ───────────────────────────────────────────────────────────────

MD_JS = r"""
function mdHtml(t){
  if(!t)return'';
  return t
    .replace(/## (.*)/g,'<h2 class="md-h2">$1</h2>')
    .replace(/\*\*(.*?)\*\*/g,'<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/^[-*] (.+)/gm,'<li class="md-li">$1</li>')
    .replace(/(<li[\s\S]*?<\/li>\n?)+/g,m=>'<ul class="md-ul">'+m+'</ul>')
    .split('\n\n').map(b=>b.startsWith('<')?b:`<p class="md-p">${b}</p>`).join('');
}
"""

# ── Full HTML assembly ─────────────────────────────────────────────────────────

def build_html(repos, trends, weekly, arxiv, recs):
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
    updated = datetime.now(timezone.utc).strftime("%d %b %Y · %H:%M UTC")

    domains    = Counter(
        (r.get("analysis_result") or {}).get("ai_domain", "")
        for r in visible
        if (r.get("analysis_result") or {}).get("ai_domain")
    )
    top_domain = domains.most_common(1)[0][0] if domains else ""

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
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,600;1,9..144,300;1,9..144,500&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#080c14;--bg2:#0d1220;--surface:#111826;--surface2:#18202e;
  --border:#1e2a3d;--border2:#28395a;
  --text:#c8d4e8;--text2:#7a8faa;--text3:#3d5070;
  --blue:#4f9cf9;--purple:#9d72ff;--green:#36d97b;
  --amber:#f5a623;--pink:#f472b6;--teal:#2dd4bf;--red:#f87171;
  --r:10px;
  --mono:'IBM Plex Mono',monospace;
  --serif:'Fraunces',serif;
  --sans:'DM Sans',sans-serif;
}}
html{{scroll-behavior:smooth}}
body{{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:15px;line-height:1.6;min-height:100vh}}
a{{color:var(--blue);text-decoration:none}}
a:hover{{text-decoration:underline}}
button{{font-family:var(--sans);cursor:pointer;border:none}}

/* Nav */
.nav{{position:sticky;top:0;z-index:200;display:flex;align-items:center;gap:1.5rem;
  padding:.85rem 2rem;background:color-mix(in srgb,var(--bg) 88%,transparent);
  border-bottom:1px solid var(--border);backdrop-filter:blur(16px)}}
.nav-brand{{font-family:var(--serif);font-size:1.1rem;font-weight:600;color:#e8f0ff;letter-spacing:-.02em;flex-shrink:0}}
.nav-brand span{{color:var(--blue)}}
.nav-tabs{{display:flex;gap:2px}}
.nav-tab{{background:none;border-bottom:2px solid transparent;color:var(--text2);
  padding:.45rem 1rem;font-size:.8rem;font-weight:500;letter-spacing:.04em;text-transform:uppercase;transition:all .2s}}
.nav-tab:hover{{color:var(--text)}}
.nav-tab.active{{color:var(--blue);border-bottom-color:var(--blue)}}
.nav-spacer{{flex:1}}
.nav-time{{font-family:var(--mono);font-size:.68rem;color:var(--text3);white-space:nowrap}}

/* Stats bar */
.stats-bar{{display:flex;align-items:center;gap:.5rem;padding:.6rem 2rem;
  background:var(--bg2);border-bottom:1px solid var(--border);flex-wrap:wrap}}
.stat{{display:flex;align-items:center;gap:.4rem;font-size:.75rem;color:var(--text2);
  padding:.2rem .7rem;background:var(--surface);border:1px solid var(--border);border-radius:99px;white-space:nowrap}}
.stat b{{color:var(--text);font-weight:500}}
.stat-div{{width:1px;height:16px;background:var(--border);margin:0 .25rem}}

/* Tab panels */
.tab-panel{{display:none;padding:1.5rem 2rem;animation:fadeIn .2s ease}}
.tab-panel.active{{display:block}}
@keyframes fadeIn{{from{{opacity:0;transform:translateY(4px)}}to{{opacity:1;transform:none}}}}

/* Toolbar */
.toolbar{{display:flex;gap:.45rem;margin-bottom:1.25rem;flex-wrap:wrap;align-items:center}}
.filter-btn{{background:var(--surface);border:1px solid var(--border);color:var(--text2);
  border-radius:8px;padding:.3rem .8rem;font-size:.75rem;transition:all .2s}}
.filter-btn:hover{{color:var(--text);border-color:var(--border2)}}
.filter-btn.active{{background:#4f9cf918;border-color:var(--blue);color:var(--blue)}}
.search-box{{margin-left:auto;background:var(--surface);border:1px solid var(--border);
  color:var(--text);border-radius:8px;padding:.3rem .85rem;font-size:.8rem;font-family:var(--sans);
  outline:none;width:220px;transition:border-color .2s}}
.search-box:focus{{border-color:var(--blue)}}
.search-box::placeholder{{color:var(--text3)}}
.count-badge{{font-family:var(--mono);font-size:.7rem;color:var(--text3)}}

/* Card grid */
.card-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:1rem}}

/* Card */
.card{{position:relative;overflow:hidden;background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);padding:1.1rem 1.1rem 1rem;
  transition:border-color .2s,transform .15s,box-shadow .2s}}
.card:hover{{border-color:var(--border2);transform:translateY(-2px);box-shadow:0 12px 40px #00000060}}
.card-accent{{position:absolute;top:0;left:0;right:0;height:2px;opacity:.7}}
.card-head{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:.75rem}}
.card-left{{display:flex;gap:.35rem;flex-wrap:wrap;align-items:center}}
.cat-badge{{font-family:var(--mono);font-size:.58rem;font-weight:600;
  padding:.15rem .5rem;border-radius:4px;letter-spacing:.04em;text-transform:uppercase}}
.cat-badge.xai{{background:#102a54;color:#60a5fa;border:1px solid #1a3d72}}
.cat-badge.trend{{background:#1e0d44;color:#a78bfa;border:1px solid #2d1c5c}}
.domain-badge{{font-size:.72rem;font-weight:500}}
.score-chip{{font-family:var(--mono);font-size:1rem;font-weight:600;
  width:40px;height:40px;border-radius:8px;display:flex;align-items:center;justify-content:center;
  border-width:1.5px;border-style:solid;flex-shrink:0}}
.card-title{{margin-bottom:.1rem}}
.card-title a{{font-size:.98rem;font-weight:500;color:#dde8ff;letter-spacing:-.01em}}
.card-title a:hover{{color:var(--blue);text-decoration:none}}
.card-owner{{font-family:var(--mono);font-size:.65rem;color:var(--text3);margin-bottom:.6rem}}
.card-problem{{font-size:.83rem;color:var(--text2);line-height:1.55;margin-bottom:.45rem;
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}}
.card-innov,.card-why{{font-size:.78rem;color:var(--text2);line-height:1.45;margin-bottom:.35rem;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.attr-row,.tag-row,.topic-row{{display:flex;gap:.3rem;flex-wrap:wrap;margin-bottom:.4rem}}
.attr{{font-size:.62rem;padding:.12rem .45rem;border-radius:4px;background:#0d2438;color:#38bdf8;border:1px solid #163654}}
.tag{{font-size:.62rem;padding:.12rem .45rem;border-radius:4px;background:#0a1f38;color:#5ba3e8}}
.tag.purple{{background:#160e30;color:#9d72ff}}
.topic{{font-size:.6rem;padding:.1rem .4rem;border-radius:4px;background:var(--surface2);color:var(--text3);border:1px solid var(--border)}}
.card-foot{{display:flex;align-items:center;gap:.6rem;border-top:1px solid var(--border);padding-top:.6rem;margin-top:.5rem}}
.stars{{font-size:.75rem;color:var(--amber);font-weight:500}}
.rel-bar{{display:flex;align-items:center;gap:.4rem;flex:1}}
.rel-lbl{{font-family:var(--mono);font-size:.6rem;color:var(--text3)}}
.rel-track{{flex:1;height:3px;background:var(--surface2);border-radius:99px;overflow:hidden}}
.rel-fill{{height:100%;border-radius:99px}}
.rel-val{{font-family:var(--mono);font-size:.62rem;color:var(--text3)}}

/* Weekly */
.weekly-wrap{{display:grid;grid-template-columns:160px 1fr;gap:1.5rem;align-items:start}}
.weekly-sidebar{{position:sticky;top:80px}}
.sidebar-lbl{{font-family:var(--mono);font-size:.62rem;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:.6rem}}
#week-list{{display:flex;flex-direction:column;gap:.3rem}}
.week-btn{{background:var(--surface);border:1px solid var(--border);color:var(--text2);
  border-radius:7px;padding:.35rem .7rem;font-size:.75rem;font-family:var(--mono);
  text-align:left;transition:all .2s}}
.week-btn:hover{{color:var(--text);background:var(--surface2)}}
.week-btn.active{{background:#4f9cf914;border-color:var(--blue);color:var(--blue)}}
.weekly-main{{min-width:0}}
.kpi-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:.75rem;margin-bottom:1.5rem}}
.kpi-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);
  padding:1rem .9rem;display:flex;flex-direction:column;align-items:center;text-align:center;gap:.15rem}}
.kpi-icon{{font-size:1.1rem;margin-bottom:.1rem}}
.kpi-val{{font-family:var(--mono);font-size:1.7rem;font-weight:600;line-height:1}}
.kpi-lbl{{font-size:.7rem;color:var(--text2)}}
.kpi-delta{{font-family:var(--mono);font-size:.68rem;font-weight:600;margin-top:.1rem}}
.kpi-delta.up{{color:var(--green)}}.kpi-delta.dn{{color:var(--red)}}.kpi-delta.flat{{color:var(--text3)}}
.weekly-body{{display:grid;grid-template-columns:1fr 260px;gap:1.2rem;align-items:start}}
.analysis-col{{min-width:0}}
.analysis-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:1.75rem}}
.charts-col{{display:flex;flex-direction:column;gap:.8rem}}
.chart-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:1rem}}
.chart-title{{font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;color:var(--text3);margin-bottom:.85rem}}
.bar-row{{display:flex;align-items:center;gap:.5rem;margin-bottom:.4rem}}
.bar-name{{font-size:.78rem;color:var(--text2);min-width:68px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.bar-track{{flex:1;background:var(--surface2);border-radius:99px;height:6px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:99px;transition:width .5s ease}}
.bar-cnt{{font-family:var(--mono);font-size:.65rem;color:var(--text3);min-width:18px;text-align:right}}
.top-repo-row{{display:flex;align-items:center;gap:.5rem;padding:.45rem .5rem;
  border-radius:6px;color:var(--text);transition:background .15s;margin-bottom:.2rem}}
.top-repo-row:hover{{background:var(--surface2);text-decoration:none}}
.top-repo-rank{{font-family:var(--mono);font-size:.65rem;color:var(--text3);min-width:22px}}
.top-repo-name{{font-size:.83rem;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.top-repo-meta{{display:flex;align-items:center;gap:.4rem;flex-shrink:0}}
.top-repo-cat{{font-size:.58rem;padding:.1rem .35rem;border-radius:3px}}
.top-repo-cat.xai{{background:#102a54;color:#60a5fa}}
.top-repo-cat.trend{{background:#1e0d44;color:#a78bfa}}
.top-repo-stars{{font-size:.72rem;color:var(--amber)}}

/* Analysis prose */
.analysis-prose .md-h2{{font-family:var(--serif);font-size:1.15rem;font-weight:600;font-style:italic;
  color:#dde8ff;margin:1.5rem 0 .65rem;padding-bottom:.5rem;border-bottom:1px solid var(--border)}}
.analysis-prose .md-h2:first-child{{margin-top:0}}
.analysis-prose .md-p{{font-size:.92rem;color:var(--text2);line-height:1.8;margin-bottom:.8rem}}
.analysis-prose .md-ul{{padding-left:1.2rem;margin-bottom:.8rem}}
.analysis-prose .md-li{{font-size:.9rem;color:var(--text2);line-height:1.7;margin-bottom:.25rem}}
.analysis-prose strong{{color:var(--text);font-weight:500}}
.analysis-prose a{{color:var(--blue)}}

/* Insight */
.insight-wrap{{display:grid;grid-template-columns:1fr 200px;gap:1.5rem;align-items:start}}
.insight-main{{min-width:0}}
.insight-sidebar{{position:sticky;top:80px}}
.pref-banner{{display:flex;align-items:flex-start;gap:.85rem;background:var(--surface);
  border:1px solid var(--border);border-left:3px solid var(--purple);
  border-radius:var(--r);padding:.85rem 1rem;margin-bottom:1.1rem}}
.pref-banner-icon{{font-size:1.3rem;flex-shrink:0;margin-top:.1rem}}
.pref-banner-body{{flex:1;min-width:0}}
.pref-summary{{font-size:.87rem;color:var(--text);margin-bottom:.4rem;line-height:1.5}}
.pref-stats{{display:flex;flex-direction:column;gap:.2rem;font-size:.78rem;color:var(--text2);flex-shrink:0}}
.insight-tabs{{display:flex;gap:.4rem;margin-bottom:1.1rem}}
.itab{{background:var(--surface);border:1px solid var(--border);color:var(--text2);
  border-radius:8px;padding:.35rem .9rem;font-size:.8rem;transition:all .2s}}
.itab:hover{{color:var(--text)}}
.itab.active{{background:#4f9cf914;border-color:var(--blue);color:var(--blue)}}
.itab-panel{{display:none}}.itab-panel.active{{display:block}}
.feed-grid{{display:flex;flex-direction:column;gap:.75rem}}
.feed-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);
  padding:1rem 1.1rem;transition:border-color .2s}}
.feed-card:hover{{border-color:var(--border2)}}
.feed-head{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:.5rem;gap:.75rem}}
.feed-title-row{{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap;flex:1;min-width:0}}
.feed-name{{font-size:.95rem;font-weight:500;color:#dde8ff}}
.feed-name:hover{{color:var(--blue);text-decoration:none}}
.feed-domain{{font-size:.76rem;font-weight:500;margin-bottom:.35rem}}
.feed-problem{{font-size:.87rem;color:var(--text2);line-height:1.55;margin-bottom:.5rem}}
.feed-actions{{display:flex;gap:.3rem;flex-shrink:0}}
.btn-like,.btn-dislike{{background:none;border:1px solid var(--border);border-radius:6px;
  padding:.2rem .5rem;font-size:.75rem;transition:all .2s}}
.btn-like{{color:var(--green)}}.btn-like:hover,.btn-like.active{{background:#0b3322;border-color:var(--green)}}
.btn-dislike{{color:var(--red)}}.btn-dislike:hover,.btn-dislike.active{{background:#2d1212;border-color:var(--red)}}
.feed-foot{{display:flex;align-items:center;gap:.7rem;margin-top:.6rem;border-top:1px solid var(--border);padding-top:.55rem}}
.score-meter{{flex:1;height:3px;background:var(--surface2);border-radius:99px;overflow:hidden}}
.score-meter-fill{{height:100%;border-radius:99px}}
.score-val{{font-family:var(--mono);font-size:.68rem;font-weight:600}}
.papers-list{{display:flex;flex-direction:column;gap:.75rem}}
.paper-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:1rem 1.1rem}}
.paper-date{{font-family:var(--mono);font-size:.65rem;color:var(--text3);margin-bottom:.3rem}}
.paper-title{{font-size:.9rem;font-weight:500;color:#c8d8f0;display:block;line-height:1.45;margin-bottom:.3rem}}
.paper-title:hover{{color:var(--blue);text-decoration:none}}
.paper-authors{{font-size:.75rem;color:var(--text3);margin-bottom:.5rem}}
.paper-abstract{{font-size:.84rem;color:var(--text2);line-height:1.65}}
.sidebar-section{{margin-bottom:1.5rem}}
.pref-row{{display:flex;align-items:center;padding:.4rem .6rem;border-radius:5px;
  font-size:.78rem;background:var(--surface);border:1px solid var(--border);
  margin-bottom:.3rem;color:var(--text2)}}
.pref-like{{border-left:2px solid var(--green)}}
.pref-dislike{{border-left:2px solid var(--red)}}

/* Empty */
.empty{{color:var(--text3);font-size:.85rem;padding:3rem;text-align:center}}
.empty-sm{{color:var(--text3);font-size:.75rem;padding:.3rem 0;font-style:italic}}

/* Responsive */
@media(max-width:1024px){{
  .weekly-body,.weekly-wrap{{grid-template-columns:1fr}}
  .weekly-sidebar{{position:static;display:flex;flex-wrap:wrap;gap:.4rem}}
  #week-list{{display:flex;flex-direction:row;flex-wrap:wrap;gap:.3rem}}
  .kpi-row{{grid-template-columns:repeat(2,1fr)}}
}}
@media(max-width:720px){{
  .nav{{padding:.7rem 1rem;gap:1rem}}
  .nav-time{{display:none}}
  .tab-panel{{padding:1rem}}
  .stats-bar{{padding:.5rem 1rem}}
  .insight-wrap{{grid-template-columns:1fr}}
  .insight-sidebar{{display:none}}
}}
</style>
</head>
<body>
<nav class="nav">
  <span class="nav-brand">⬡ <span>AI</span> Hub</span>
  <div class="nav-tabs">
    <button class="nav-tab active" onclick="switchTab('repos',this)">Repos</button>
    <button class="nav-tab" onclick="switchTab('weekly',this)">Weekly</button>
    <button class="nav-tab" onclick="switchTab('insight',this)">Insight</button>
  </div>
  <span class="nav-spacer"></span>
  <span class="nav-time">{updated}</span>
</nav>

<div class="stats-bar">
  <span class="stat">📦 Total <b>{total}</b></span>
  <span class="stat-div"></span>
  <span class="stat">🔍 XAI <b>{xai_n}</b></span>
  <span class="stat">🔥 Trending <b>{trend_n}</b></span>
  {f'<span class="stat-div"></span><span class="stat">🏆 Top domain <b>{top_domain}</b></span>' if top_domain else ""}
</div>

<div class="tab-panel active" id="tab-repos">
  <div class="toolbar">
    <button class="filter-btn active" onclick="filterCards('all',this)">All</button>
    <button class="filter-btn" onclick="filterCards('XAI',this)">XAI only</button>
    <button class="filter-btn" onclick="filterCards('Trending AI',this)">Trending</button>
    <button class="filter-btn" onclick="filterCards('high',this)">Score ≥ 70</button>
    <button class="filter-btn" onclick="filterCards('GenAI',this)">GenAI</button>
    <button class="filter-btn" onclick="filterCards('NLP',this)">NLP</button>
    <button class="filter-btn" onclick="filterCards('Multimodal',this)">Multimodal</button>
    <input class="search-box" type="text" placeholder="Search repos, tech, domain…" oninput="searchCards(this.value)">
    <span class="count-badge" id="count-badge">{total} repos</span>
  </div>
  <div class="card-grid" id="card-grid">{cards_html}</div>
</div>

<div class="tab-panel" id="tab-weekly">{weekly_html}</div>
<div class="tab-panel" id="tab-insight">{insight_html}</div>

<script>
{MD_JS}
function switchTab(name,btn){{
  document.querySelectorAll('.nav-tab').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-'+name).classList.add('active');
}}
let _activeFilter='all',_searchQ='';
function filterCards(type,btn){{
  document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');_activeFilter=type;_applyFilters();
}}
function searchCards(q){{_searchQ=q.toLowerCase().trim();_applyFilters();}}
function _applyFilters(){{
  let v=0;
  document.querySelectorAll('.card').forEach(c=>{{
    const cat=c.dataset.cat,score=parseFloat(c.dataset.score||0),dom=c.dataset.domain||'',src=c.dataset.search||'';
    const byFilter=_activeFilter==='all'||((_activeFilter==='XAI')&&cat==='XAI')||((_activeFilter==='Trending AI')&&cat==='Trending AI')||(_activeFilter==='high'&&score>=70)||(_activeFilter===dom);
    const bySearch=!_searchQ||src.includes(_searchQ);
    const show=byFilter&&bySearch;c.style.display=show?'':'none';if(show)v++;
  }});
  const b=document.getElementById('count-badge');if(b)b.textContent=v+' repos';
}}
</script>
</body>
</html>'''

# ── Entry point ────────────────────────────────────────────────────────────────

def export_all():
    db = get_client()
    print("📡 Fetching data from Supabase…")
    repos, trends, weekly, arxiv, recs = fetch_all(db)
    print(f"  repos={len(repos)} trends={len(trends)} weekly={len(weekly)} arxiv={len(arxiv)} recs={len(recs)}")
    html = build_html(repos, trends, weekly, arxiv, recs)
    os.makedirs("output", exist_ok=True)
    path = "output/index.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"🎉 Exported → {path}  ({len(html.encode())//1024} KB)")

if __name__ == "__main__":
    export_all()
