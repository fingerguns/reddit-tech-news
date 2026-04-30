#!/usr/bin/env python3
"""
Reddit Tech News Scraper
Fetches top posts from popular tech subreddits and generates a static HTML page.
Usage: python scraper.py
       python scraper.py --output my_page.html
       python scraper.py --limit 20 --min-score 50
"""

import argparse
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("Missing dependency: run  pip install requests")
    sys.exit(1)

# ── Configuration ─────────────────────────────────────────────────────────────

SUBREDDITS = [
    # General tech
    {"name": "technology",      "label": "Technology",       "color": "#ff6314"},
    {"name": "tech",            "label": "Tech",             "color": "#e74c3c"},
    # AI / ML
    {"name": "MachineLearning", "label": "Machine Learning", "color": "#9b59b6"},
    {"name": "artificial",      "label": "Artificial Intel.", "color": "#8e44ad"},
    {"name": "singularity",     "label": "Singularity",      "color": "#6c3483"},
    # Software & Dev
    {"name": "programming",     "label": "Programming",      "color": "#3498db"},
    {"name": "webdev",          "label": "Web Dev",          "color": "#2980b9"},
    {"name": "devops",          "label": "DevOps",           "color": "#1abc9c"},
    {"name": "Python",          "label": "Python",           "color": "#27ae60"},
    {"name": "javascript",      "label": "JavaScript",       "color": "#f39c12"},
    {"name": "rust",            "label": "Rust",             "color": "#e67e22"},
    {"name": "golang",          "label": "Go",               "color": "#16a085"},
    # Security
    {"name": "netsec",          "label": "Net Security",     "color": "#c0392b"},
    {"name": "cybersecurity",   "label": "Cyber Security",   "color": "#a93226"},
    # Hardware & Science
    {"name": "hardware",        "label": "Hardware",         "color": "#7f8c8d"},
    {"name": "linux",           "label": "Linux",            "color": "#f1c40f"},
    {"name": "compsci",         "label": "Comp. Sci.",       "color": "#2ecc71"},
    {"name": "datascience",     "label": "Data Science",     "color": "#d35400"},
]

HEADERS = {
    "User-Agent": "TechNewsScraper/1.0 (personal use; https://github.com/)",
    "Accept": "application/json",
}

POSTS_PER_SUB  = 25   # posts to fetch per subreddit per endpoint
EMBED_PER_CARD = 25   # posts to embed per card (JS picks top 5 from these)
MIN_SCORE      = 10   # minimum upvote score to display
REQUEST_DELAY  = 2.0  # seconds between requests (Reddit recommends ≥2s unauthenticated)

# ── Fetch ──────────────────────────────────────────────────────────────────────

def _fetch_endpoint(url: str, retries: int = 3) -> list[dict]:
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=12)
            if r.status_code == 429:
                wait = 10 * (2 ** attempt)
                print(f"  ⏳ Rate limited — waiting {wait}s before retry…")
                time.sleep(wait)
                continue
            r.raise_for_status()
            children = r.json().get("data", {}).get("children", [])
            return [c["data"] for c in children if not c["data"].get("stickied")]
        except requests.RequestException:
            if attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
    return []


def fetch_subreddit(name: str, limit: int = POSTS_PER_SUB) -> list[dict]:
    """Fetch both hot and monthly-top posts, merge by post ID for full time coverage."""
    merged: dict[str, dict] = {}
    for url in [
        f"https://www.reddit.com/r/{name}/hot.json?limit={limit}",
        f"https://www.reddit.com/r/{name}/top.json?t=month&limit={limit}",
    ]:
        for post in _fetch_endpoint(url):
            merged.setdefault(post["id"], post)
        time.sleep(REQUEST_DELAY)
    return list(merged.values())


def fetch_all(min_score: int = MIN_SCORE) -> dict[str, list[dict]]:
    results: dict[str, list[dict]] = {}
    total = len(SUBREDDITS)
    for i, sub in enumerate(SUBREDDITS, 1):
        name = sub["name"]
        print(f"  [{i:2}/{total}] r/{name} …", end=" ", flush=True)
        posts    = fetch_subreddit(name)
        filtered = [p for p in posts if p.get("score", 0) >= min_score]
        results[name] = filtered
        print(f"{len(filtered)} posts")
    return results


# ── Helpers ────────────────────────────────────────────────────────────────────

def relative_time(utc_ts: float) -> str:
    now = datetime.now(timezone.utc).timestamp()
    diff = int(now - utc_ts)
    if diff < 60:
        return "just now"
    if diff < 3600:
        return f"{diff // 60}m ago"
    if diff < 86400:
        return f"{diff // 3600}h ago"
    return f"{diff // 86400}d ago"


def short_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        return host.replace("www.", "")
    except Exception:
        return ""


def reddit_link(post: dict) -> str:
    return f"https://www.reddit.com{post['permalink']}"


def fmt_num(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


# ── Top-5 selection ───────────────────────────────────────────────────────────

_STOP = {
    "a","an","the","is","are","was","were","be","been","have","has","had",
    "do","does","did","will","would","could","should","may","might","to",
    "of","in","for","on","with","at","by","from","as","or","and","but",
    "not","this","that","it","its","we","i","he","she","they","its","new",
    "says","say","said","over","just","how","what","why","when","who","get",
}

def _words(title: str) -> frozenset:
    tokens = re.sub(r"[^a-z0-9 ]", "", title.lower()).split()
    return frozenset(t for t in tokens if t not in _STOP and len(t) > 1)

def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

def select_top5(all_posts: dict[str, list[dict]], n: int = 5) -> list[dict]:
    flat = [p for posts in all_posts.values() for p in posts]
    flat.sort(key=lambda p: p.get("score", 0), reverse=True)

    picked, seen_words, seen_urls = [], [], set()
    for post in flat:
        if len(picked) >= n:
            break
        norm_url = post.get("url", "").split("?")[0].rstrip("/")
        if norm_url in seen_urls:
            continue
        words = _words(post.get("title", ""))
        if any(_jaccard(words, sw) >= 0.4 for sw in seen_words):
            continue
        picked.append(post)
        seen_words.append(words)
        seen_urls.add(norm_url)
    return picked


# ── HTML Generation ────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Tech News — Reddit Digest</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --bg:        #0f1117;
      --surface:   #1a1d27;
      --surface2:  #22263a;
      --border:    #2e3347;
      --text:      #e8eaf0;
      --muted:     #8b90a7;
      --accent:    #5c6bc0;
      --green:     #4caf82;
      --yellow:    #f0c040;
      --red:       #e05252;
      --radius:    10px;
      --font:      'Inter', 'Segoe UI', system-ui, sans-serif;
    }}

    html {{ scroll-behavior: smooth; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: var(--font);
      font-size: 14px;
      line-height: 1.6;
      min-height: 100vh;
    }}

    /* ── Header ── */
    header {{
      position: sticky;
      top: 0;
      z-index: 100;
      background: rgba(15,17,23,0.92);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
      padding: 14px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}
    .logo {{
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.3px;
    }}
    .logo svg {{ color: #ff6314; }}
    .generated {{
      font-size: 12px;
      color: var(--muted);
    }}
    .refresh-btn {{
      background: var(--surface2);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 6px 14px;
      border-radius: 6px;
      font-size: 12px;
      cursor: pointer;
      text-decoration: none;
      transition: border-color 0.15s;
    }}
    .refresh-btn:hover {{ border-color: var(--accent); }}

    /* ── Filter bar ── */
    .filter-bar {{
      padding: 14px 24px;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      border-bottom: 1px solid var(--border);
      background: var(--surface);
    }}
    .filter-btn {{
      border: 1px solid var(--border);
      background: var(--surface2);
      color: var(--muted);
      padding: 4px 12px;
      border-radius: 20px;
      font-size: 12px;
      cursor: pointer;
      transition: all 0.15s;
    }}
    .filter-btn.active, .filter-btn:hover {{
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }}

    /* ── Search + time filters ── */
    .search-wrap {{
      padding: 16px 24px 0;
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
    }}
    #search {{
      flex: 1;
      min-width: 180px;
      max-width: 420px;
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 8px 14px;
      border-radius: 8px;
      font-size: 14px;
      outline: none;
      transition: border-color 0.15s;
    }}
    #search:focus {{ border-color: var(--accent); }}
    #search::placeholder {{ color: var(--muted); }}
    .time-btns {{
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }}
    .time-btn {{
      border: 1px solid var(--border);
      background: var(--surface2);
      color: var(--muted);
      padding: 6px 13px;
      border-radius: 8px;
      font-size: 12px;
      font-family: var(--font);
      cursor: pointer;
      transition: all 0.15s;
      white-space: nowrap;
    }}
    .time-btn:hover {{
      border-color: var(--accent);
      color: var(--text);
    }}
    .time-btn.active {{
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }}

    /* ── Top 5 ── */
    .top5-wrap {{
      padding: 24px 24px 0;
      display: flex;
      justify-content: center;
    }}
    .top5-card {{
      width: 100%;
      max-width: 720px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
      position: relative;
    }}
    .top5-card::before {{
      content: '';
      display: block;
      height: 3px;
      background: linear-gradient(90deg, #f0c040, #ff6314, #9b59b6);
    }}
    .top5-header {{
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 13px 18px;
      border-bottom: 1px solid var(--border);
    }}
    .top5-header-title {{
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.02em;
      text-transform: uppercase;
      color: var(--yellow);
    }}
    .top5-header-sub {{
      font-size: 11px;
      color: var(--muted);
      margin-left: 4px;
    }}
    .top5-item {{
      display: flex;
      align-items: flex-start;
      gap: 14px;
      padding: 12px 18px;
      border-bottom: 1px solid var(--border);
      transition: background 0.12s;
    }}
    .top5-item:last-child {{ border-bottom: none; }}
    .top5-item:hover {{ background: var(--surface2); }}
    .top5-item.hidden {{ display: none; }}
    .top5-rank {{
      font-size: 20px;
      font-weight: 800;
      min-width: 28px;
      text-align: right;
      line-height: 1.2;
      padding-top: 1px;
      color: #4a5068;
    }}
    .top5-rank.r1 {{ color: #f0c040; -webkit-text-stroke: 0; }}
    .top5-rank.r2 {{ color: #b0bec5; -webkit-text-stroke: 0; }}
    .top5-rank.r3 {{ color: #cd7f32; -webkit-text-stroke: 0; }}
    .top5-body {{ flex: 1; min-width: 0; }}
    .top5-title {{
      font-size: 14px;
      font-weight: 600;
      line-height: 1.4;
      color: var(--text);
      text-decoration: none;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}
    .top5-title:hover {{ color: #a5b4fc; }}
    .top5-title:visited {{ color: #9ca3af; }}
    .top5-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 5px;
      font-size: 11px;
      color: var(--muted);
      align-items: center;
    }}
    .top5-sub-badge {{
      padding: 1px 7px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 600;
      color: #fff;
    }}
    .top5-score {{
      color: var(--yellow);
      font-weight: 600;
    }}

    /* ── Grid ── */
    main {{
      padding: 20px 24px 40px;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
      gap: 20px;
    }}

    /* ── Subreddit card ── */
    .sub-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }}
    .sub-card.hidden {{ display: none; }}
    .sub-header {{
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 12px 16px;
      border-bottom: 1px solid var(--border);
    }}
    .sub-dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      flex-shrink: 0;
    }}
    .sub-name {{
      font-weight: 600;
      font-size: 13px;
    }}
    .sub-name a {{
      color: var(--text);
      text-decoration: none;
    }}
    .sub-name a:hover {{ text-decoration: underline; }}
    .sub-count {{
      margin-left: auto;
      font-size: 11px;
      color: var(--muted);
      background: var(--surface2);
      padding: 2px 8px;
      border-radius: 10px;
    }}

    /* ── Post list ── */
    .post-list {{ list-style: none; padding: 0; }}
    .post-item {{
      display: flex;
      gap: 10px;
      padding: 10px 16px;
      border-bottom: 1px solid var(--border);
      transition: background 0.12s;
    }}
    .post-item:last-child {{ border-bottom: none; }}
    .post-item:hover {{ background: var(--surface2); }}

    .score-col {{
      display: flex;
      flex-direction: column;
      align-items: center;
      min-width: 36px;
      padding-top: 2px;
    }}
    .score-arrow {{
      color: var(--accent);
      font-size: 10px;
      line-height: 1;
    }}
    .score-num {{
      font-size: 11px;
      font-weight: 600;
      color: var(--yellow);
    }}

    .post-body {{ flex: 1; min-width: 0; }}
    .post-title {{
      font-size: 13px;
      font-weight: 500;
      line-height: 1.4;
      color: var(--text);
      text-decoration: none;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}
    .post-title:hover {{ color: #a5b4fc; }}
    .post-title:visited {{ color: #9ca3af; }}

    .post-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 5px;
      font-size: 11px;
      color: var(--muted);
      align-items: center;
    }}
    .post-domain {{
      background: var(--surface2);
      padding: 1px 6px;
      border-radius: 4px;
      font-size: 10px;
    }}
    .post-comments {{
      color: var(--muted);
      text-decoration: none;
      font-size: 11px;
    }}
    .post-comments:hover {{ color: var(--text); }}
    .flair {{
      background: rgba(92,107,192,0.2);
      color: #a5b4fc;
      padding: 1px 6px;
      border-radius: 4px;
      font-size: 10px;
      max-width: 120px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .nsfw-badge {{
      background: rgba(224,82,82,0.2);
      color: var(--red);
      padding: 1px 6px;
      border-radius: 4px;
      font-size: 10px;
    }}

    /* ── Empty state ── */
    .empty {{ padding: 24px 16px; text-align: center; color: var(--muted); font-size: 13px; }}
    .card-empty-msg {{
      padding: 18px 16px;
      text-align: center;
      color: var(--muted);
      font-size: 12px;
      font-style: italic;
    }}

    /* ── Footer ── */
    footer {{
      text-align: center;
      padding: 16px;
      font-size: 11px;
      color: var(--muted);
      border-top: 1px solid var(--border);
    }}
    footer a {{ color: var(--muted); }}

    @media (max-width: 600px) {{
      main {{ padding: 12px; gap: 12px; }}
      header {{ padding: 10px 12px; }}
      .filter-bar {{ padding: 10px 12px; }}
      .search-wrap {{ padding: 10px 12px 0; }}
    }}
  </style>
</head>
<body>

<header>
  <div class="logo">
    <svg width="22" height="22" viewBox="0 0 20 20" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
      <circle cx="10" cy="10" r="10"/>
      <path fill="#fff" d="M16.67 10a1.46 1.46 0 0 0-2.47-1 7.16 7.16 0 0 0-3.85-1.22l.65-3.08 2.13.45a1 1 0 1 0 .1-.49l-2.38-.5a.12.12 0 0 0-.14.09l-.73 3.43a7.15 7.15 0 0 0-3.87 1.22 1.46 1.46 0 1 0-1.61 2.37 2.84 2.84 0 0 0 0 .38c0 1.94 2.26 3.51 5.05 3.51s5.05-1.57 5.05-3.51a2.84 2.84 0 0 0 0-.38 1.46 1.46 0 0 0 .02-2.27ZM7.5 10.75a.75.75 0 1 1 .75.75.75.75 0 0 1-.75-.75Zm4.2 2a2.77 2.77 0 0 1-1.7.46 2.77 2.77 0 0 1-1.7-.46.15.15 0 0 1 .2-.22 2.47 2.47 0 0 0 1.5.37 2.47 2.47 0 0 0 1.5-.37.15.15 0 1 1 .2.22Zm-.2-1.27a.75.75 0 1 1 .75-.75.75.75 0 0 1-.75.75Z"/>
    </svg>
    Tech News — Reddit Digest
  </div>
  <span class="generated">Generated {generated_at}</span>
  <a class="refresh-btn" href="#" onclick="location.reload()">↻ Refresh</a>
</header>

<div class="filter-bar" id="filterBar">
  <button class="filter-btn active" data-filter="all" onclick="filterSubs('all', this)">All</button>
  {filter_buttons}
</div>

<div class="search-wrap">
  <input id="search" type="text" placeholder="Search posts…" oninput="applyFilters()" />
  <div class="time-btns">
    <button class="time-btn" data-window="86400"   onclick="setTimeWindow(86400, this)">Past day</button>
    <button class="time-btn" data-window="604800"  onclick="setTimeWindow(604800, this)">Past week</button>
    <button class="time-btn" data-window="2592000" onclick="setTimeWindow(2592000, this)">Past month</button>
  </div>
</div>

<div class="top5-wrap" id="top5-wrap">
  <div class="top5-card">
    <div class="top5-header">
      <span class="top5-header-title">&#x26A1; Top 5</span>
      <span class="top5-header-sub">highest-scored stories &middot; duplicates removed</span>
    </div>
    <div id="top5-items"></div>
  </div>
</div>

<main id="grid">
{cards}
</main>

<footer>
  Data sourced from <a href="https://www.reddit.com" target="_blank">Reddit</a> public API ·
  {total_posts} posts across {total_subs} subreddits ·
  <a href="https://www.reddit.com/r/technology" target="_blank">r/technology</a>
</footer>

{script_block}
</body>
</html>
"""


def build_post_html(post: dict) -> str:
    title      = html.escape(post.get("title", "")[:200])
    score      = post.get("score", 0)
    num_comms  = post.get("num_comments", 0)
    created    = post.get("created_utc", 0)
    domain     = html.escape(short_domain(post.get("url", "")))
    flair      = html.escape((post.get("link_flair_text") or "")[:40])
    nsfw       = post.get("over_18", False)
    permalink  = reddit_link(post)
    ext_url    = post.get("url", permalink)
    # If the link goes back to reddit itself, point to the comments thread
    if "reddit.com" in ext_url or "redd.it" in ext_url:
        ext_url = permalink

    flair_tag  = f'<span class="flair">{flair}</span>' if flair else ""
    nsfw_tag   = '<span class="nsfw-badge">NSFW</span>' if nsfw else ""
    domain_tag = f'<span class="post-domain">{domain}</span>' if domain else ""

    return f"""
    <li class="post-item" data-created="{int(created)}" data-score="{score}">
      <div class="score-col">
        <span class="score-arrow">▲</span>
        <span class="score-num">{fmt_num(score)}</span>
      </div>
      <div class="post-body">
        <a class="post-title" href="{html.escape(ext_url)}" target="_blank" rel="noopener">{title}</a>
        <div class="post-meta">
          {domain_tag}
          <span>{relative_time(created)}</span>
          <a class="post-comments" href="{html.escape(permalink)}" target="_blank" rel="noopener">
            💬 {fmt_num(num_comms)}
          </a>
          {flair_tag}
          {nsfw_tag}
        </div>
      </div>
    </li>"""


def build_top5_html(top5: list[dict]) -> str:
    sub_color = {s["name"]: s["color"] for s in SUBREDDITS}
    rank_class = {1: "r1", 2: "r2", 3: "r3"}
    rows = ""
    for i, post in enumerate(top5, 1):
        title    = html.escape(post.get("title", "")[:200])
        score    = post.get("score", 0)
        created  = post.get("created_utc", 0)
        num_comm = post.get("num_comments", 0)
        sub_name = post.get("subreddit", "")
        domain   = html.escape(short_domain(post.get("url", "")))
        permalink = reddit_link(post)
        ext_url  = post.get("url", permalink)
        if "reddit.com" in ext_url or "redd.it" in ext_url:
            ext_url = permalink
        color    = sub_color.get(sub_name, "#5c6bc0")
        rc       = rank_class.get(i, "")
        domain_tag = f'<span class="post-domain">{domain}</span>' if domain else ""
        rows += f"""
    <div class="top5-item" data-created="{int(created)}">
      <span class="top5-rank {rc}">{i}</span>
      <div class="top5-body">
        <a class="top5-title" href="{html.escape(ext_url)}" target="_blank" rel="noopener">{title}</a>
        <div class="top5-meta">
          <span class="top5-sub-badge" style="background:{color}">r/{html.escape(sub_name)}</span>
          <span class="top5-score">▲ {fmt_num(score)}</span>
          {domain_tag}
          <span>{relative_time(created)}</span>
          <a class="post-comments" href="{html.escape(permalink)}" target="_blank" rel="noopener">💬 {fmt_num(num_comm)}</a>
        </div>
      </div>
    </div>"""

    return f"""<div class="top5-wrap">
  <div class="top5-card">
    <div class="top5-header">
      <span class="top5-header-title">⚡ Top 5</span>
      <span class="top5-header-sub">highest-scored stories across all subreddits · duplicates removed</span>
    </div>
    {rows}
  </div>
</div>"""


def build_card_html(sub_info: dict, posts: list[dict], embed_limit: int = EMBED_PER_CARD) -> str:
    name   = sub_info["name"]
    label  = sub_info["label"]
    color  = sub_info["color"]
    # Embed top posts by score; JS will re-rank and slice to 5 per time window
    pool   = sorted(posts, key=lambda p: p.get("score", 0), reverse=True)[:embed_limit]

    items_html = "".join(build_post_html(p) for p in pool)
    count = len(pool)
    return f"""
  <div class="sub-card" data-sub="{html.escape(name)}">
    <div class="sub-header">
      <span class="sub-dot" style="background:{color}"></span>
      <span class="sub-name">
        <a href="https://www.reddit.com/r/{html.escape(name)}" target="_blank" rel="noopener">r/{html.escape(label)}</a>
      </span>
      <span class="sub-count" data-total="{count}"><span class="sub-count-num">{count}</span> posts</span>
    </div>
    <ul class="post-list">{items_html}</ul>
    <div class="card-empty-msg" style="display:none">No posts in this time window.</div>
  </div>"""


def build_script_block(posts_json: str, colors_json: str) -> str:
    return f"""<script>
const ALL_POSTS   = {posts_json};
const SUB_COLORS  = {colors_json};

const STOP_WORDS = new Set([
  "a","an","the","is","are","was","were","be","been","have","has","had",
  "do","does","did","will","would","could","should","may","might","to",
  "of","in","for","on","with","at","by","from","as","or","and","but",
  "not","this","that","it","its","we","i","he","she","they","new",
  "says","say","said","over","just","how","what","why","when","who","get"
]);

function titleWords(title) {{
  const tokens = title.toLowerCase().replace(/[^a-z0-9 ]/g, '').split(/\\s+/);
  return new Set(tokens.filter(t => t.length > 1 && !STOP_WORDS.has(t)));
}}

function jaccard(a, b) {{
  let inter = 0;
  a.forEach(w => {{ if (b.has(w)) inter++; }});
  return (a.size + b.size - inter) ? inter / (a.size + b.size - inter) : 0;
}}

function selectTop5(posts) {{
  const sorted = [...posts].sort((a, b) => b.score - a.score);
  const picked = [], seenWords = [], seenUrls = new Set();
  for (const post of sorted) {{
    if (picked.length >= 5) break;
    const normUrl = (post.url || '').split('?')[0].replace(/\\/+$/, '');
    if (seenUrls.has(normUrl)) continue;
    const w = titleWords(post.title);
    if (seenWords.some(sw => jaccard(w, sw) >= 0.4)) continue;
    picked.push(post);
    seenWords.push(w);
    seenUrls.add(normUrl);
  }}
  return picked;
}}

function fmtNum(n) {{
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
  return String(n);
}}

function relTime(ts) {{
  const diff = Math.floor(Date.now() / 1000) - ts;
  if (diff < 60)    return 'just now';
  if (diff < 3600)  return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return Math.floor(diff / 86400) + 'd ago';
}}

function esc(s) {{
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

const RANK_COLORS = ['#f0c040', '#b0bec5', '#cd7f32', '#4a5068', '#4a5068'];

function renderTop5(timeWindow) {{
  const now      = Math.floor(Date.now() / 1000);
  const filtered = timeWindow === 0
    ? ALL_POSTS
    : ALL_POSTS.filter(p => (now - p.created) <= timeWindow);
  const top5     = selectTop5(filtered);
  const container = document.getElementById('top5-items');
  if (!container) return;

  if (top5.length === 0) {{
    container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--muted);font-size:13px">No posts found in this time window.</div>';
    return;
  }}

  container.innerHTML = top5.map((post, i) => {{
    const color     = SUB_COLORS[post.sub] || '#5c6bc0';
    const rankColor = RANK_COLORS[i];
    const domainTag = post.domain ? `<span class="post-domain">${{esc(post.domain)}}</span>` : '';
    return `
    <div class="top5-item" data-created="${{post.created}}">
      <span class="top5-rank" style="color:${{rankColor}}">${{i + 1}}</span>
      <div class="top5-body">
        <a class="top5-title" href="${{esc(post.url)}}" target="_blank" rel="noopener">${{esc(post.title)}}</a>
        <div class="top5-meta">
          <span class="top5-sub-badge" style="background:${{color}}">r/${{esc(post.sub)}}</span>
          <span class="top5-score">&#x25B2; ${{fmtNum(post.score)}}</span>
          ${{domainTag}}
          <span>${{relTime(post.created)}}</span>
          <a class="post-comments" href="${{esc(post.permalink)}}" target="_blank" rel="noopener">&#x1F4AC; ${{fmtNum(post.comments)}}</a>
        </div>
      </div>
    </div>`;
  }}).join('');

  // re-apply search after re-render
  const q = document.getElementById('search').value.toLowerCase();
  if (q) {{
    document.querySelectorAll('.top5-item').forEach(item => {{
      const text = item.querySelector('.top5-title')?.textContent.toLowerCase() || '';
      item.classList.toggle('hidden', !text.includes(q));
    }});
  }}
}}

let activeSubFilter  = 'all';
let activeTimeWindow = 86400; // default: past day

function filterSubs(filter, btn) {{
  activeSubFilter = filter;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyFilters();
}}

function setTimeWindow(seconds, btn) {{
  if (activeTimeWindow === seconds) {{
    activeTimeWindow = 0;
    btn.classList.remove('active');
  }} else {{
    activeTimeWindow = seconds;
    document.querySelectorAll('.time-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  }}
  renderTop5(activeTimeWindow);
  applyFilters();
}}

function applyFilters() {{
  const q   = document.getElementById('search').value.toLowerCase();
  const now = Math.floor(Date.now() / 1000);

  document.querySelectorAll('.sub-card').forEach(card => {{
    const items = [...card.querySelectorAll('.post-item')];

    // Hide all first, then pick top 5 within the active time + search window
    items.forEach(i => i.style.display = 'none');

    const matching = items.filter(item => {{
      const created = parseInt(item.dataset.created || '0', 10);
      const text    = item.querySelector('.post-title')?.textContent.toLowerCase() || '';
      const inTime  = activeTimeWindow === 0 || (now - created) <= activeTimeWindow;
      const inSearch = !q || text.includes(q);
      return inTime && inSearch;
    }});

    matching
      .sort((a, b) => parseInt(b.dataset.score || '0') - parseInt(a.dataset.score || '0'))
      .slice(0, 5)
      .forEach(i => i.style.display = '');

    const shown    = matching.slice(0, 5).length;
    const countEl  = card.querySelector('.sub-count-num');
    const emptyMsg = card.querySelector('.card-empty-msg');
    if (countEl)  countEl.textContent = shown;
    if (emptyMsg) emptyMsg.style.display = shown === 0 ? '' : 'none';

    const subMatch = activeSubFilter === 'all' || card.dataset.sub === activeSubFilter;
    card.style.display = (subMatch && shown > 0) ? '' : 'none';
  }});

  // Search filter on Top 5 items (time filtering is handled by renderTop5)
  document.querySelectorAll('.top5-item').forEach(item => {{
    const text = item.querySelector('.top5-title')?.textContent.toLowerCase() || '';
    item.classList.toggle('hidden', !!(q && !text.includes(q)));
  }});
}}

document.addEventListener('DOMContentLoaded', () => {{
  const dayBtn = document.querySelector('.time-btn[data-window="86400"]');
  if (dayBtn) dayBtn.classList.add('active');
  renderTop5(activeTimeWindow);
  applyFilters();
}});
</script>"""


def build_html(all_posts: dict[str, list[dict]]) -> str:
    cards_html  = ""
    filter_btns = ""
    total_posts = 0
    active_subs = 0
    all_post_data: list[dict] = []

    for sub in SUBREDDITS:
        name  = sub["name"]
        posts = all_posts.get(name, [])
        if not posts:
            continue
        active_subs += 1
        total_posts += min(len(posts), EMBED_PER_CARD)
        cards_html  += build_card_html(sub, posts, EMBED_PER_CARD)
        filter_btns += f'<button class="filter-btn" data-filter="{html.escape(name)}" onclick="filterSubs(\'{html.escape(name)}\', this)">{html.escape(sub["label"])}</button>\n  '
        for p in posts:
            ext_url = p.get("url", "")
            permalink = reddit_link(p)
            if "reddit.com" in ext_url or "redd.it" in ext_url:
                ext_url = permalink
            all_post_data.append({
                "title":    p.get("title", ""),
                "score":    p.get("score", 0),
                "created":  int(p.get("created_utc", 0)),
                "url":      ext_url,
                "permalink": permalink,
                "sub":      name,
                "comments": p.get("num_comments", 0),
                "domain":   short_domain(p.get("url", "")),
            })

    sub_colors = {s["name"]: s["color"] for s in SUBREDDITS}
    posts_json = json.dumps(all_post_data, ensure_ascii=False)
    colors_json = json.dumps(sub_colors, ensure_ascii=False)
    generated_at = datetime.now().strftime("%b %d, %Y at %H:%M")

    script_block = build_script_block(posts_json, colors_json)

    return HTML_TEMPLATE.format(
        generated_at=generated_at,
        filter_buttons=filter_btns,
        cards=cards_html,
        script_block=script_block,
        total_posts=total_posts,
        total_subs=active_subs,
    )


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Reddit Tech News Scraper")
    parser.add_argument("--output",    default="index.html", help="Output HTML file (default: index.html)")
    parser.add_argument("--min-score", type=int, default=MIN_SCORE, help=f"Minimum post score (default: {MIN_SCORE})")
    parser.add_argument("--open",      action="store_true", help="Open the page in a browser when done")
    args = parser.parse_args()

    print("Reddit Tech News Scraper")
    print("=" * 40)
    print(f"Fetching hot posts from {len(SUBREDDITS)} subreddits…\n")

    all_posts = fetch_all(min_score=args.min_score)

    print(f"\nBuilding HTML…")
    page_html = build_html(all_posts)

    out_path = Path(args.output)
    out_path.write_text(page_html, encoding="utf-8")
    print(f"✓ Saved → {out_path.resolve()}")

    if args.open:
        import webbrowser
        webbrowser.open(out_path.resolve().as_uri())
        print("✓ Opened in browser")


if __name__ == "__main__":
    main()
