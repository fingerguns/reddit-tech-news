#!/usr/bin/env python3
"""
Reddit + Hacker News + TechMeme Tech Digest
Fetches from Reddit subreddits,
Hacker News top stories from the last 30 days (Algolia Search API; Firebase fallback),
and TechMeme (official RSS), generates a static HTML page.
Usage: python scraper.py
       python scraper.py --output my_page.html
       python scraper.py --min-score 50
"""

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from collections import defaultdict

try:
    import requests
except ImportError:
    print("Missing dependency: run  pip install requests")
    sys.exit(1)

# ── Configuration ─────────────────────────────────────────────────────────────

SUBREDDITS = [
    # ── Original digest ───────────────────────────────────────────
    {"name": "technology",      "label": "Technology",       "color": "#ff6314"},
    {"name": "tech",            "label": "Tech",             "color": "#e74c3c"},
    {"name": "MachineLearning", "label": "Machine Learning", "color": "#9b59b6"},
    {"name": "artificial",      "label": "Artificial Intel.", "color": "#8e44ad"},
    {"name": "singularity",     "label": "Singularity",      "color": "#6c3483"},
    {"name": "programming",     "label": "Programming",      "color": "#3498db"},
    {"name": "webdev",          "label": "Web Dev",          "color": "#2980b9"},
    {"name": "devops",          "label": "DevOps",           "color": "#1abc9c"},
    {"name": "Python",          "label": "Python",           "color": "#27ae60"},
    {"name": "javascript",      "label": "JavaScript",       "color": "#f39c12"},
    {"name": "rust",            "label": "Rust",             "color": "#e67e22"},
    {"name": "golang",          "label": "Go",               "color": "#16a085"},
    {"name": "netsec",          "label": "Net Security",     "color": "#c0392b"},
    {"name": "cybersecurity",   "label": "Cyber Security",   "color": "#a93226"},
    {"name": "hardware",        "label": "Hardware",         "color": "#7f8c8d"},
    {"name": "linux",           "label": "Linux",            "color": "#f1c40f"},
    {"name": "compsci",         "label": "Comp. Sci.",       "color": "#2ecc71"},
    {"name": "datascience",     "label": "Data Science",     "color": "#d35400"},
    # ── Languages & runtimes ─────────────────────────────────────
    {"name": "java",            "label": "Java",             "color": "#5382a1"},
    {"name": "Kotlin",          "label": "Kotlin",           "color": "#7f52ff"},
    {"name": "scala",           "label": "Scala",            "color": "#dc322f"},
    {"name": "Clojure",         "label": "Clojure",          "color": "#5881d8"},
    {"name": "cpp",             "label": "C++",              "color": "#00599c"},
    {"name": "C_Programming",   "label": "C",                "color": "#283593"},
    {"name": "csharp",          "label": "C#",               "color": "#68217a"},
    {"name": "ruby",            "label": "Ruby",             "color": "#cc342d"},
    {"name": "php",             "label": "PHP",              "color": "#777bb4"},
    {"name": "swift",           "label": "Swift",            "color": "#f05138"},
    {"name": "dartlang",        "label": "Dart",             "color": "#0175c2"},
    {"name": "elixir",          "label": "Elixir",           "color": "#6e4a9e"},
    {"name": "haskell",         "label": "Haskell",          "color": "#5d4f85"},
    {"name": "zig",             "label": "Zig",              "color": "#f7a41d"},
    {"name": "typescript",      "label": "TypeScript",       "color": "#3178c6"},
    # ── Frontend & UI ─────────────────────────────────────────────
    {"name": "reactjs",         "label": "React",            "color": "#61dafb"},
    {"name": "vuejs",           "label": "Vue.js",           "color": "#42b883"},
    {"name": "angular",         "label": "Angular",          "color": "#dd0031"},
    {"name": "nextjs",          "label": "Next.js",          "color": "#94a3b8"},
    {"name": "sveltejs",        "label": "Svelte",           "color": "#ff3e00"},
    {"name": "tailwindcss",     "label": "Tailwind",         "color": "#38bdf8"},
    {"name": "css",             "label": "CSS",              "color": "#264de4"},
    {"name": "Frontend",        "label": "Frontend",         "color": "#00bcd4"},
    # ── Infra, ops & cloud ───────────────────────────────────────
    {"name": "sysadmin",        "label": "Sysadmin",         "color": "#546e7a"},
    {"name": "selfhosted",      "label": "Self-hosted",      "color": "#00897b"},
    {"name": "homelab",         "label": "Homelab",          "color": "#5e35b1"},
    {"name": "kubernetes",      "label": "Kubernetes",       "color": "#326ce5"},
    {"name": "docker",          "label": "Docker",           "color": "#2496ed"},
    {"name": "terraform",       "label": "Terraform",        "color": "#844fba"},
    {"name": "ansible",         "label": "Ansible",          "color": "#ee0000"},
    {"name": "aws",             "label": "AWS",              "color": "#ff9900"},
    {"name": "azure",           "label": "Azure",            "color": "#0078d4"},
    {"name": "googlecloud",     "label": "Google Cloud",     "color": "#4285f4"},
    {"name": "cloudcomputing",  "label": "Cloud",            "color": "#039be5"},
    # ── Mobile & platforms ───────────────────────────────────────
    {"name": "androiddev",      "label": "Android Dev",      "color": "#3ddc84"},
    {"name": "iOSProgramming",  "label": "iOS",              "color": "#147efb"},
    {"name": "FlutterDev",      "label": "Flutter",          "color": "#02569b"},
    {"name": "dotnet",          "label": ".NET",             "color": "#512bd4"},
    {"name": "windows",         "label": "Windows",          "color": "#00a4ef"},
    {"name": "MacOS",           "label": "macOS",            "color": "#999999"},
    # ── Data & ML adjacent ─────────────────────────────────────────
    {"name": "nlp",             "label": "NLP",              "color": "#8e44ad"},
    {"name": "ComputerVision",  "label": "Computer Vision",  "color": "#9b59b6"},
    {"name": "LocalLLaMA",      "label": "Local LLM",        "color": "#6c3483"},
    {"name": "OpenAI",          "label": "OpenAI",           "color": "#10a37f"},
    {"name": "StableDiffusion", "label": "Stable Diffusion", "color": "#48b092"},
    {"name": "PostgreSQL",      "label": "PostgreSQL",       "color": "#336791"},
    {"name": "Database",        "label": "Database",         "color": "#607d8b"},
    {"name": "SQL",             "label": "SQL",              "color": "#4479a1"},
    {"name": "BusinessIntelligence", "label": "BI",        "color": "#ff8f00"},
    {"name": "analytics",       "label": "Analytics",        "color": "#00897b"},
    # ── Security adjacent ──────────────────────────────────────────
    {"name": "ReverseEngineering", "label": "Reverse Eng.",  "color": "#b71c1c"},
    {"name": "Malware",         "label": "Malware",          "color": "#c62828"},
    {"name": "privacy",         "label": "Privacy",          "color": "#37474f"},
    {"name": "PrivacyToolsIO",  "label": "Privacy Tools",    "color": "#455a64"},
    {"name": "TOR",             "label": "Tor",              "color": "#7e57c2"},
    {"name": "opensourceintelligence", "label": "OSINT",         "color": "#5d4037"},
    # ── Hardware & electronics ───────────────────────────────────
    {"name": "buildapc",        "label": "Build a PC",       "color": "#0288d1"},
    {"name": "nvidia",          "label": "NVIDIA",           "color": "#76b900"},
    {"name": "AMD",             "label": "AMD",              "color": "#ed1c24"},
    {"name": "arduino",         "label": "Arduino",          "color": "#00979d"},
    {"name": "electronics",     "label": "Electronics",    "color": "#fbc02d"},
    {"name": "FPGA",            "label": "FPGA",             "color": "#6a1b9a"},
    {"name": "embedded",        "label": "Embedded",       "color": "#0277bd"},
    {"name": "Apple",           "label": "Apple",            "color": "#a3aaae"},
    {"name": "Android",         "label": "Android",          "color": "#3ddc84"},
    # ── Games & graphics ─────────────────────────────────────────
    {"name": "gamedev",         "label": "Game Dev",         "color": "#7cb342"},
    {"name": "Unity3D",         "label": "Unity",            "color": "#222c37"},
    {"name": "unrealengine",    "label": "Unreal",           "color": "#111"},
    {"name": "GraphicsProgramming", "label": "Graphics",   "color": "#ec407a"},
    {"name": "Vulkan",          "label": "Vulkan",           "color": "#ac162c"},
    # ── Science & robotics ───────────────────────────────────────
    {"name": "Futurology",      "label": "Futurology",       "color": "#00acc1"},
    {"name": "science",         "label": "Science",          "color": "#43a047"},
    {"name": "Physics",         "label": "Physics",          "color": "#1565c0"},
    {"name": "SpaceX",          "label": "SpaceX",           "color": "#bdbdbd"},
    {"name": "NASA",            "label": "NASA",             "color": "#0d47a1"},
    {"name": "robotics",        "label": "Robotics",         "color": "#ef6c00"},
    {"name": "bioinformatics",  "label": "Bioinformatics",   "color": "#2e7d32"},
    # ── Industry & products ──────────────────────────────────────
    {"name": "startups",        "label": "Startups",         "color": "#ef5350"},
    {"name": "SaaS",            "label": "SaaS",             "color": "#5c6bc0"},
    {"name": "ProductManagement", "label": "Product",        "color": "#8d6e63"},
    {"name": "UXDesign",        "label": "UX Design",        "color": "#ab47bc"},
    {"name": "technews",        "label": "Tech News",        "color": "#78909c"},
    {"name": "gadgets",         "label": "Gadgets",          "color": "#26a69a"},
]

HEADERS = {
    "User-Agent": "TechNewsScraper/1.0 (personal use; https://github.com/)",
    "Accept": "application/json, application/rss+xml, text/xml;q=0.9, */*;q=0.8",
}

TECHMEME_FEED_URL = "https://www.techmeme.com/feed.xml"
TECHMEME_FETCH_N  = 40  # RSS items to ingest per run
_TM_OUTBOUND_HREF = re.compile(r'href="(https?://[^"]+)"', re.I)

POSTS_PER_SUB  = 25   # posts to fetch per subreddit per endpoint
EMBED_PER_CARD = 25   # posts to embed per card (JS picks top 5 from these)
MIN_SCORE      = 10   # minimum upvote score to display
REQUEST_DELAY  = 2.0  # seconds between requests (Reddit recommends ≥2s unauthenticated)

# HN: Algolia Search API — stories in rolling window, ranked by popularity in the index.
HN_ALGOLIA_URL           = "https://hn.algolia.com/api/v1/search"
HN_WINDOW_DAYS         = 30
HN_ALGOLIA_HITS_PER_PAGE = 100
HN_ALGOLIA_MAX_PAGES     = 5  # up to 500 hits before dedupe
# Fallback if Algolia fails — Firebase official API (current front page only).
HN_TOP_URL  = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"
HN_FETCH_N  = 80

# Cards below Top 5: all Reddit subs + Hacker News + TechMeme (source labels JS/CSS)
CARD_FEEDS = [{**s, "source": "reddit"} for s in SUBREDDITS] + [
    {"name": "hackernews", "label": "Hacker News", "color": "#f59e0b", "source": "hackernews"},
    {"name": "techmeme", "label": "TechMeme", "color": "#14b8a6", "source": "techmeme"},
]
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
        filtered = [{**p, "source": "reddit"} for p in posts if p.get("score", 0) >= min_score]
        results[name] = filtered
        print(f"{len(filtered)} posts")
    return results


def normalize_algolia_hit(hit: dict) -> dict | None:
    """Map Algolia HN search hit to the same shape as Firebase items."""
    title = (hit.get("title") or "").strip()
    if not title:
        return None
    try:
        hid = int(hit["objectID"])
    except (KeyError, TypeError, ValueError):
        return None
    url = (hit.get("url") or "").strip()
    permalink = f"https://news.ycombinator.com/item?id={hid}"
    if not url:
        url = permalink
    return {
        "id": f"hn_{hid}",
        "title": title,
        "score": int(hit.get("points") or 0),
        "created_utc": float(hit.get("created_at_i") or 0),
        "url": url,
        "permalink": permalink,
        "num_comments": int(hit.get("num_comments") or 0),
        "source": "hackernews",
        "subreddit": "hackernews",
        "link_flair_text": None,
        "over_18": False,
    }


def normalize_hn_item(raw: dict | None) -> dict | None:
    if not raw or raw.get("type") != "story":
        return None
    if raw.get("dead") or raw.get("deleted"):
        return None
    hid = raw["id"]
    url = raw.get("url") or f"https://news.ycombinator.com/item?id={hid}"
    permalink = f"https://news.ycombinator.com/item?id={hid}"
    return {
        "id": f"hn_{hid}",
        "title": raw.get("title", ""),
        "score": int(raw.get("score") or 0),
        "created_utc": float(raw.get("time") or 0),
        "url": url,
        "permalink": permalink,
        "num_comments": int(raw.get("descendants") or 0),
        "source": "hackernews",
        "subreddit": "hackernews",
        "link_flair_text": None,
        "over_18": False,
    }


def _fetch_hackernews_algolia_recent(min_score: int) -> list[dict]:
    """Top stories from the last HN_WINDOW_DAYS (Algolia index ranking ≈ popularity)."""
    cutoff = int(datetime.now(timezone.utc).timestamp()) - HN_WINDOW_DAYS * 86400
    by_id: dict[int, dict] = {}
    page = 0
    while page < HN_ALGOLIA_MAX_PAGES:
        try:
            r = requests.get(
                HN_ALGOLIA_URL,
                params={
                    "tags": "story",
                    "numericFilters": f"created_at_i>{cutoff}",
                    "hitsPerPage": HN_ALGOLIA_HITS_PER_PAGE,
                    "page": page,
                },
                headers=HEADERS,
                timeout=22,
            )
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError, TypeError):
            break

        hits = data.get("hits") or []
        if not hits:
            break

        for hit in hits:
            row = normalize_algolia_hit(hit)
            if not row or row["score"] < min_score:
                continue
            hid = int(hit["objectID"])
            prev = by_id.get(hid)
            if prev is None or row["score"] > prev["score"]:
                by_id[hid] = row

        nb_pages = int(data.get("nbPages") or 0)
        page += 1
        if page >= nb_pages:
            break

    return sorted(by_id.values(), key=lambda p: p["score"], reverse=True)


def _fetch_hackernews_firebase(min_score: int) -> list[dict]:
    """Legacy: current front page via Firebase (used only if Algolia fails)."""
    try:
        r = requests.get(HN_TOP_URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
        ids = r.json()[:HN_FETCH_N]
    except requests.RequestException:
        return []

    out: list[dict] = []
    for hid in ids:
        try:
            ir = requests.get(HN_ITEM_URL.format(hid), headers=HEADERS, timeout=10)
            ir.raise_for_status()
            row = normalize_hn_item(ir.json())
            if row and row["score"] >= min_score:
                out.append(row)
        except requests.RequestException:
            continue
    return out


def fetch_hackernews(min_score: int = MIN_SCORE) -> list[dict]:
    """HN stories from the last ~30 days (Algolia); Firebase front page if Algolia is unavailable."""
    posts = _fetch_hackernews_algolia_recent(min_score)
    if posts:
        return posts
    return _fetch_hackernews_firebase(min_score)


def _techmeme_outbound_url(description: str, fallback: str) -> str:
    """TechMeme RSS <link> points at the river permalink; article URL lives in HTML description."""
    if not description:
        return fallback
    for m in _TM_OUTBOUND_HREF.finditer(description):
        u = m.group(1)
        if "techmeme.com" not in u.lower():
            return u
    return fallback


def _parse_rfc822_ts(pub: str) -> float:
    if not pub or not pub.strip():
        return 0.0
    try:
        return parsedate_to_datetime(pub.strip()).timestamp()
    except (TypeError, ValueError):
        return 0.0


def fetch_techmeme(min_score: int = MIN_SCORE) -> list[dict]:
    """TechMeme homepage river via official RSS.

    Items are newest-first in the feed; we assign synthetic scores so the UI ranks by that
    feed order (not votes — unlike Reddit/HN scores).
    """
    try:
        r = requests.get(TECHMEME_FEED_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except (requests.RequestException, ET.ParseError):
        return []

    out: list[dict] = []
    for i, item in enumerate(root.findall(".//item")):
        if len(out) >= TECHMEME_FETCH_N:
            break
        title_el = item.find("title")
        link_el = item.find("link")
        pub_el = item.find("pubDate")
        desc_el = item.find("description")
        title = (title_el.text or "").strip() if title_el is not None and title_el.text else ""
        permalink = (link_el.text or "").strip() if link_el is not None and link_el.text else ""
        if not title or not permalink:
            continue
        desc = (desc_el.text or "") if desc_el is not None and desc_el.text else ""
        pub = (pub_el.text or "").strip() if pub_el is not None and pub_el.text else ""
        article = _techmeme_outbound_url(desc, permalink)
        created = _parse_rfc822_ts(pub)
        # Synthetic score preserves RSS order inside the TechMeme pool (no Reddit-style votes).
        score = 10_000 - i * 10
        out.append({
            "id": f"tm_{hashlib.sha256(permalink.encode()).hexdigest()[:12]}",
            "title": title,
            "score": score,
            "created_utc": created,
            "url": article,
            "permalink": permalink,
            "num_comments": 0,
            "source": "techmeme",
            "subreddit": "techmeme",
            "link_flair_text": None,
            "over_18": False,
        })
    return out


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


def story_link(post: dict) -> str:
    """Outbound article URL for the post title."""
    if post.get("source") == "hackernews":
        u = (post.get("url") or "").strip()
        if u.startswith("http") and "news.ycombinator.com" not in u:
            return u
        return post["permalink"]
    if post.get("source") == "techmeme":
        u = (post.get("url") or "").strip()
        if u.startswith("http"):
            return u
        return post.get("permalink") or u
    permalink = reddit_link(post)
    ext_url = post.get("url", permalink)
    if "reddit.com" in ext_url or "redd.it" in ext_url:
        ext_url = permalink
    return ext_url


def comments_link(post: dict) -> str:
    """Thread / comments URL."""
    if post.get("source") == "hackernews":
        return post["permalink"]
    if post.get("source") == "techmeme":
        return post.get("permalink") or story_link(post)
    return reddit_link(post)


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
  <title>Fingerguns: Reddit, HN &amp; TechMeme digest</title>
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
      /* Source cues — cool violet (Reddit) vs warm amber (HN), far apart on the spectrum */
      --src-reddit:       #8b5cf6;
      --src-reddit-soft:  #a78bfa;
      --src-reddit-deep:  #6d28d9;
      --src-hn:           #f59e0b;
      --src-hn-soft:      #fbbf24;
      --src-hn-deep:      #d97706;
      --src-tm:           #14b8a6;
      --src-tm-soft:      #2dd4bf;
      --src-tm-deep:      #0d9488;
      --digest-rail-w: min(22rem, 34vw);
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

    /* ── Narrative digest rail (HN + Reddit + TechMeme) ── */
    .digest-body-wrap {{
      padding-right: calc(var(--digest-rail-w) + 1rem);
      min-height: 100vh;
    }}
    .digest-rail {{
      position: fixed;
      top: 0;
      right: 0;
      width: var(--digest-rail-w);
      height: 100vh;
      overflow-y: auto;
      -webkit-overflow-scrolling: touch;
      scrollbar-gutter: stable;
      background: var(--surface);
      border-left: 1px solid var(--border);
      z-index: 85;
      font-size: 13px;
    }}
    .digest-rail-inner {{
      padding: 72px 16px 32px;
    }}
    .digest-rail-headline {{
      font-size: 14px;
      font-weight: 700;
      line-height: 1.35;
      letter-spacing: -0.02em;
      color: var(--text);
      margin: 0 0 8px;
    }}
    .digest-rail-lede {{
      font-size: 11px;
      line-height: 1.55;
      color: var(--muted);
      margin: 0 0 16px;
    }}
    .digest-rail-toggle {{
      display: flex;
      gap: 0;
      margin: 0 0 14px;
      border: 1px solid var(--border);
      border-radius: 6px;
      overflow: hidden;
    }}
    .digest-rail-btn {{
      flex: 1;
      border: none;
      background: transparent;
      color: var(--muted);
      font-family: var(--font);
      font-size: 10px;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      padding: 8px 4px;
      cursor: pointer;
      transition: background 0.15s ease, color 0.15s ease;
    }}
    .digest-rail-btn + .digest-rail-btn {{
      border-left: 1px solid var(--border);
    }}
    .digest-rail-btn[aria-pressed="true"] {{
      background: rgba(92,107,192,0.28);
      color: var(--text);
    }}
    .digest-rail-summary {{
      margin: 0;
      font-size: 12.5px;
      line-height: 1.65;
      color: var(--text);
      font-family: var(--font);
    }}
    .digest-topic {{
      margin: 0 0 1rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid var(--border);
    }}
    .digest-topic:last-child {{
      border-bottom: none;
      padding-bottom: 0;
      margin-bottom: 0;
    }}
    .digest-topic-title {{
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--accent);
      margin: 0 0 6px;
    }}
    .digest-topic-body {{
      font-size: 12.5px;
      line-height: 1.65;
      color: var(--text);
    }}
    .digest-rail-summary.digest-rail-muted {{
      color: var(--muted);
    }}
    .digest-rail-meta {{
      margin: 16px 0 0;
      font-size: 10px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted);
      line-height: 1.5;
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
      font-size: 17px;
      font-weight: 700;
      letter-spacing: -0.3px;
    }}
    .generated {{
      font-size: 12px;
      color: var(--muted);
    }}

    /* ── Filter bar ── */
    .filter-bar {{
      padding: 14px 24px;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      background: transparent;
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
    /* None & All — keep neutral accent */
    .filter-btn:not([data-source]):hover,
    .filter-btn:not([data-source]).active {{
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }}
    .filter-btn[data-source="reddit"] {{
      border-color: rgba(139, 92, 246, 0.42);
      color: var(--src-reddit-soft);
      background: rgba(139, 92, 246, 0.1);
    }}
    .filter-btn[data-source="reddit"]:hover {{
      border-color: var(--src-reddit);
      background: rgba(139, 92, 246, 0.22);
      color: #ede9fe;
    }}
    .filter-btn[data-source="reddit"].active {{
      background: rgba(139, 92, 246, 0.32);
      border-color: var(--src-reddit-soft);
      color: #fff;
    }}
    .filter-btn[data-source="hackernews"] {{
      border-color: rgba(245, 158, 11, 0.45);
      color: var(--src-hn-soft);
      background: rgba(245, 158, 11, 0.1);
    }}
    .filter-btn[data-source="hackernews"]:hover {{
      border-color: var(--src-hn);
      background: rgba(245, 158, 11, 0.22);
      color: #fffbeb;
    }}
    .filter-btn[data-source="hackernews"].active {{
      background: rgba(245, 158, 11, 0.32);
      border-color: var(--src-hn-soft);
      color: #fff;
    }}
    .filter-btn[data-source="techmeme"] {{
      border-color: rgba(20, 184, 166, 0.45);
      color: var(--src-tm-soft);
      background: rgba(20, 184, 166, 0.1);
    }}
    .filter-btn[data-source="techmeme"]:hover {{
      border-color: var(--src-tm);
      background: rgba(20, 184, 166, 0.22);
      color: #ccfbf1;
    }}
    .filter-btn[data-source="techmeme"].active {{
      background: rgba(20, 184, 166, 0.32);
      border-color: var(--src-tm-soft);
      color: #fff;
    }}

    /* ── Feed drawer (mobile): collapsed by default ── */
    .filter-drawer {{
      border-bottom: 1px solid var(--border);
      background: var(--surface);
    }}
    .filter-drawer-toggle {{
      display: none;
      width: 100%;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 12px 24px;
      border: none;
      border-bottom: 1px solid transparent;
      background: var(--surface);
      color: var(--text);
      font-family: var(--font);
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      text-align: left;
      transition: background 0.15s;
    }}
    .filter-drawer-toggle:hover {{
      background: var(--surface2);
    }}
    .filter-drawer-chevron {{
      flex-shrink: 0;
      font-size: 12px;
      color: var(--muted);
      transition: transform 0.2s ease;
    }}
    .filter-drawer.is-open .filter-drawer-chevron {{
      transform: rotate(180deg);
    }}
    .filter-drawer-panel {{
      display: block;
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
    .source-btns {{
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }}
    .source-label {{
      font-size: 11px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .source-btn {{
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
    .source-btn:hover {{ color: var(--text); }}
    .source-btn.active[data-src="reddit"] {{
      border-color: var(--src-reddit);
      background: rgba(139,92,246,0.14);
      color: var(--src-reddit-soft);
    }}
    .source-btn.active[data-src="hackernews"] {{
      border-color: var(--src-hn);
      background: rgba(245,158,11,0.14);
      color: var(--src-hn-soft);
    }}
    .source-btn.active[data-src="techmeme"] {{
      border-color: var(--src-tm);
      background: rgba(20,184,166,0.14);
      color: var(--src-tm-soft);
    }}

    /* ── Top 5 row ── */
    .top5-row {{
      padding: 24px 24px 0;
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      justify-content: center;
      max-width: 1480px;
      margin: 0 auto;
    }}
    .top5-col {{
      flex: 1 1 300px;
      max-width: 520px;
      min-width: 260px;
    }}
    .top5-card {{
      width: 100%;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
      position: relative;
    }}
    .top5-card--reddit::before {{
      content: '';
      display: block;
      height: 3px;
      background: linear-gradient(90deg, var(--src-reddit-soft), var(--src-reddit), var(--src-reddit-deep));
    }}
    .top5-card--hn::before {{
      content: '';
      display: block;
      height: 3px;
      background: linear-gradient(90deg, var(--src-hn-soft), var(--src-hn), var(--src-hn-deep));
    }}
    .top5-card--tm::before {{
      content: '';
      display: block;
      height: 3px;
      background: linear-gradient(90deg, var(--src-tm-soft), var(--src-tm), var(--src-tm-deep));
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
    .sub-card[data-source="reddit"] {{
      border-left: 4px solid var(--src-reddit);
    }}
    .sub-card[data-source="hackernews"] {{
      border-left: 4px solid var(--src-hn);
    }}
    .sub-card[data-source="techmeme"] {{
      border-left: 4px solid var(--src-tm);
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
    /* TechMeme: RSS items have no Reddit/HN-style votes or comment counts here */
    .sub-card[data-source="techmeme"] .score-col,
    .sub-card[data-source="techmeme"] .post-comments {{
      display: none;
    }}
    #techmeme-top5-items .top5-score,
    #techmeme-top5-items .post-comments {{
      display: none;
    }}
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

    @media (max-width: 960px) {{
      .digest-body-wrap {{ padding-right: 0; }}
      .digest-rail {{
        position: relative;
        width: 100%;
        height: auto;
        min-height: 0;
        border-left: none;
        border-top: 1px solid var(--border);
        z-index: 1;
      }}
      .digest-rail-inner {{
        padding: 24px 16px 28px;
      }}
    }}

    @media (max-width: 600px) {{
      main {{ padding: 12px; gap: 12px; }}
      header {{ padding: 10px 12px; }}
      .filter-bar {{ padding: 10px 12px; border-bottom: none; }}
      .search-wrap {{ padding: 10px 12px 0; }}
      .filter-drawer-toggle {{
        display: flex;
        padding: 10px 12px;
      }}
      .filter-drawer-panel {{
        display: none;
        max-height: min(52vh, 400px);
        overflow-y: auto;
        -webkit-overflow-scrolling: touch;
      }}
      .filter-drawer.is-open .filter-drawer-panel {{
        display: block;
      }}
    }}
  </style>
</head>
<body>
<div class="digest-body-wrap">

<header>
  <div class="logo">Fingerguns: Reddit, HN &amp; TechMeme digest</div>
  <span class="generated">Generated {generated_at}</span>
</header>

<div class="filter-drawer" id="filterDrawer">
  <button type="button" class="filter-drawer-toggle" id="filterDrawerToggle" onclick="toggleFilterDrawer()" aria-expanded="false" aria-controls="filterDrawerPanel">
    <span class="filter-drawer-toggle-label">Browse feeds</span>
    <span class="filter-drawer-chevron" aria-hidden="true">▾</span>
  </button>
  <div class="filter-drawer-panel" id="filterDrawerPanel">
<div class="filter-bar" id="filterBar">
  <button class="filter-btn active" data-filter="none" onclick="filterSubs('none', this)">None</button>
  <button class="filter-btn" data-filter="all" onclick="filterSubs('all', this)">All</button>
  {filter_buttons}
</div>
  </div>
</div>

<div class="search-wrap">
  <input id="search" type="text" placeholder="Search posts…" oninput="applyFilters()" />
  <div class="time-btns">
    <span class="source-label">When</span>
    <button class="time-btn" data-window="86400"   onclick="setTimeWindow(86400, this)">Past day</button>
    <button class="time-btn" data-window="604800"  onclick="setTimeWindow(604800, this)">Past week</button>
    <button class="time-btn" data-window="2592000" onclick="setTimeWindow(2592000, this)">Past month</button>
  </div>
  <div class="source-btns">
    <span class="source-label">Source</span>
    <button type="button" class="source-btn active" data-src="reddit" onclick="toggleSource(this)">Reddit</button>
    <button type="button" class="source-btn active" data-src="hackernews" onclick="toggleSource(this)">Hacker News</button>
    <button type="button" class="source-btn active" data-src="techmeme" onclick="toggleSource(this)">TechMeme</button>
  </div>
</div>

<div class="top5-row" id="top5-row">
  <div class="top5-col" data-source-panel="reddit">
    <div class="top5-card top5-card--reddit">
      <div class="top5-header">
        <span class="top5-header-title">Reddit Top 5</span>
        <span class="top5-header-sub">across tech subs &middot; duplicates removed</span>
      </div>
      <div id="reddit-top5-items"></div>
    </div>
  </div>
  <div class="top5-col" data-source-panel="hackernews">
    <div class="top5-card top5-card--hn">
      <div class="top5-header">
        <span class="top5-header-title">Hacker News Top 5</span>
        <span class="top5-header-sub">past 30 days &middot; duplicates removed</span>
      </div>
      <div id="hn-top5-items"></div>
    </div>
  </div>
  <div class="top5-col" data-source-panel="techmeme">
    <div class="top5-card top5-card--tm">
      <div class="top5-header">
        <span class="top5-header-title">TechMeme Latest 5</span>
        <span class="top5-header-sub">RSS river order (newest first) &middot; duplicates removed</span>
      </div>
      <div id="techmeme-top5-items"></div>
    </div>
  </div>
</div>

<main id="grid">
{cards}
</main>

<footer>
  Data from <a href="https://www.reddit.com" target="_blank">Reddit</a> public API,
  <a href="https://hn.algolia.com/api" target="_blank">Hacker News</a> (Algolia Search; <a href="https://github.com/HackerNews/API" target="_blank">Firebase</a> fallback),
  &amp; <a href="https://www.techmeme.com/" target="_blank">TechMeme</a> RSS
  &middot; {total_posts} posts in grid &middot; Generated locally once daily
</footer>

</div><!-- .digest-body-wrap -->

<aside class="digest-rail" aria-label="The past day in tech summary">
  <div class="digest-rail-inner">
    <h2 class="digest-rail-headline">The past day in tech -- a summary</h2>
    <p class="digest-rail-lede">Themes from Reddit, Hacker News, and TechMeme for the window you pick below. Regenerated on each daily scrape.</p>
    <div class="digest-rail-toggle" role="group" aria-label="Summary time window">
      <button type="button" class="digest-rail-btn" data-digest-period="day" aria-pressed="true">Day</button>
      <button type="button" class="digest-rail-btn" data-digest-period="week" aria-pressed="false">Week</button>
      <button type="button" class="digest-rail-btn" data-digest-period="month" aria-pressed="false">Month</button>
    </div>
    <div id="digest-rail-summary" class="digest-rail-summary digest-rail-muted" role="region" aria-label="Summary body">Loading…</div>
    <p id="digest-rail-meta" class="digest-rail-meta" aria-live="polite"></p>
  </div>
</aside>

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
    flair_raw  = post.get("link_flair_text") or ""
    flair      = html.escape(str(flair_raw)[:40])
    nsfw       = post.get("over_18", False)
    permalink  = comments_link(post)
    ext_url    = story_link(post)

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
    src    = sub_info["source"]
    # Embed top posts by score; JS will re-rank and slice to 5 per time window
    pool   = sorted(posts, key=lambda p: p.get("score", 0), reverse=True)[:embed_limit]

    items_html = "".join(build_post_html(p) for p in pool)
    count = len(pool)
    if src == "hackernews":
        sub_title = (
            f'<a href="https://news.ycombinator.com/" target="_blank" rel="noopener">'
            f'{html.escape(label)}</a>'
        )
    elif src == "techmeme":
        sub_title = (
            f'<a href="https://www.techmeme.com/" target="_blank" rel="noopener">'
            f'{html.escape(label)}</a>'
        )
    else:
        sub_title = (
            f'<a href="https://www.reddit.com/r/{html.escape(name)}" target="_blank" '
            f'rel="noopener">r/{html.escape(label)}</a>'
        )
    return f"""
  <div class="sub-card" data-sub="{html.escape(name)}" data-source="{html.escape(src)}">
    <div class="sub-header">
      <span class="sub-dot" style="background:{color}"></span>
      <span class="sub-name">{sub_title}</span>
      <span class="sub-count" data-total="{count}"><span class="sub-count-num">{count}</span> posts</span>
    </div>
    <ul class="post-list">{items_html}</ul>
    <div class="card-empty-msg" style="display:none">No posts in this time window.</div>
  </div>"""


DEFAULT_SUMMARY_TOPIC = "Industry & products"

# Keyword buckets → sidebar topic headings (first match wins by score).
SUMMARY_TOPICS: list[tuple[str, tuple[str, ...]]] = [
    ("Artificial intelligence & policy", (
        "openai", "anthropic", "claude", "gpt-", "chatgpt", "gemini", "copilot",
        "machine learning", " llm", "large language", "deepmind", "xai", "grok",
        " neural", "diffusion", "stable diffusion", "midjourney", "mistral",
        "artificial intelligence",
    )),
    ("Courts, trials & accountability", (
        "trial", "lawsuit", "court", "judge", "doj ", "sec ", "ftc", "subpoena",
        "testimony", "verdict", "settlement", "antitrust", "musk", "altman",
    )),
    ("Meta & social platforms", (
        "meta ", "facebook", "instagram", "whatsapp", "threads", "oculus",
        "smart glasses", "ray-ban",
    )),
    ("Markets & finance", (
        "bond", "ipo", "valuation", "raised ", "funding", "vc ", "prediction market",
        "investors", " billion", "million seed",
    )),
    ("Security & crypto", (
        "hack", "ransomware", "cve-", "vulnerability", "zero-day", "malware",
        "cryptocurrency", "bitcoin", "ethereum", "defi", "wallet", "north korea",
        "breach", "stolen", "drift protocol",
    )),
    ("Europe & infrastructure", (
        "eu ", "european", "gdpr", "spain", "germany", "france", "belgium",
        "parliament", "brussels", "laliga", "nuclear", "decommission",
    )),
    ("Browsers, OSS & dev tooling", (
        "mozilla", "chrome", "firefox", "webkit", "browser", "open source",
        " zig ", "gcc ", "llvm", "kernel",
    )),
    ("Consumer tech & chips", (
        "apple ", "iphone", "ipad", "google ", "android", "youtube", "windows ",
        "microsoft ", "steam", "nvidia", "amd ", "intel ", "raspberry pi",
    )),
    ("Science & research", (
        "study finds", "research", "scientists", "paper ", "journal ",
        " genome", "biology", "physics", "climate",
    )),
]

SUMMARY_TOPIC_ORDER = [t[0] for t in SUMMARY_TOPICS] + [DEFAULT_SUMMARY_TOPIC]


def _classify_summary_topic(title: str) -> str:
    tl = (title or "").lower()
    best_score = 0
    best_name = DEFAULT_SUMMARY_TOPIC
    for name, keys in SUMMARY_TOPICS:
        score = sum(1 for k in keys if k in tl)
        if score > best_score:
            best_score = score
            best_name = name
    return best_name


_DIGEST_TITLE_PREFIX = re.compile(r"^(Show HN|Ask HN|Tell HN):\s*", re.IGNORECASE)


def _digest_clause_from_title(title: str) -> str:
    """Short clause for fallback prose — no quotation marks, not a headline paste."""
    t = _DIGEST_TITLE_PREFIX.sub("", title).strip()
    if not t:
        return ""
    return _truncate_prose(t, 118)


def _synthesize_topic_text(titles: list[str]) -> str:
    """Fallback narrative: framed paragraphs that weave themes, not quoted headline lists."""
    clauses = [_digest_clause_from_title(t) for t in titles if t.strip()]
    clauses = [c for c in clauses if c]
    if not clauses:
        return ""
    if len(clauses) == 1:
        return _truncate_prose(
            "This bucket mostly hinged on one storyline worth watching: "
            f"{clauses[0]}. The discussion treated it as the focal point rather than background noise.",
            720,
        )
    if len(clauses) == 2:
        return _truncate_prose(
            "Two angles kept resurfacing: "
            f"{clauses[0]}; separately, coverage also leaned toward {clauses[1]}.",
            720,
        )
    # 3+ clauses: weave without quoting
    head = clauses[0]
    mid = clauses[1:-1]
    tail = clauses[-1]
    bridge = "; ".join(mid) if mid else ""
    if bridge:
        core = f"{head}; {bridge}; and {tail}"
    else:
        core = f"{head}; and {tail}"
    core = _truncate_prose(core, 520)
    return _truncate_prose(
        "Across Hacker News, Reddit, and TechMeme the signal condensed into a single ongoing thread: "
        f"{core}. Nothing here reads as one isolated post—the overlap is what gives it weight.",
        780,
    )


def _fallback_topic_sections(posts: list[dict], *, max_topics: int = 8, max_per_topic: int = 4) -> list[dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    seen_urls: set[str] = set()
    ranked = sorted(posts, key=lambda p: int(p.get("score") or 0), reverse=True)
    for p in ranked:
        url = (p.get("url") or "").split("?")[0].rstrip("/").lower()
        if url:
            if url in seen_urls:
                continue
            seen_urls.add(url)
        title = (p.get("title") or "").strip()
        if not title:
            continue
        topic = _classify_summary_topic(title)
        if len(buckets[topic]) >= max_per_topic:
            continue
        buckets[topic].append(p)

    sections: list[dict] = []
    for topic in SUMMARY_TOPIC_ORDER:
        items = buckets.get(topic, [])
        if not items:
            continue
        titles = [(x.get("title") or "").strip() for x in items]
        text = _synthesize_topic_text(titles)
        if text:
            sections.append({"topic": topic, "text": text})
        if len(sections) >= max_topics:
            break
    return sections


def _truncate_prose(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    cut = s[:max_len].rstrip()
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "…"


def _titles_for_summaries(posts: list[dict], cap: int = 22) -> list[str]:
    ranked = sorted(posts, key=lambda p: int(p.get("score") or 0), reverse=True)
    out: list[str] = []
    for p in ranked[:cap]:
        t = (p.get("title") or "").strip()
        if t:
            out.append(t)
    return out


def _normalize_period_sections(val: object) -> list[dict]:
    """Coerce LLM JSON (or legacy flat string) into validated topic sections."""
    if isinstance(val, str):
        s = val.strip()
        return [{"topic": "Overview", "text": s}] if s else []
    if not isinstance(val, list):
        return []
    out: list[dict] = []
    for item in val:
        if not isinstance(item, dict):
            continue
        topic = str(item.get("topic", "")).strip()
        body = str(item.get("text", "")).strip()
        if topic and body:
            out.append({"topic": topic[:180], "text": body[:4200]})
    return out


def _openai_feed_summaries(bundles_prompt: str) -> dict[str, list[dict]] | None:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    payload = {
        "model": model,
        "response_format": {"type": "json_object"},
        "temperature": 0.55,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write editorial sidebar summaries from noisy headline lists (Reddit, Hacker News, TechMeme). "
                    "Return JSON only. Each period is an array of {topic, text}. "
                    "Never paste headlines verbatim, never wrap text in quotation marks, never bullet enumerations. "
                    "Paraphrase into flowing prose."
                ),
            },
            {
                "role": "user",
                "content": bundles_prompt,
            },
        ],
    }
    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        r.raise_for_status()
        body = r.json()
        raw = body["choices"][0]["message"]["content"]
        parsed = json.loads(raw)
        sections_map = {
            k: _normalize_period_sections(parsed.get(k)) for k in ("day", "week", "month")
        }
        if sum(len(v) for v in sections_map.values()) == 0:
            return None
        return sections_map
    except (requests.RequestException, KeyError, json.JSONDecodeError, IndexError):
        return None


def build_feed_summaries(all_posts: dict[str, list[dict]]) -> dict[str, object]:
    """Topical summaries for day/week/month from Reddit + HN + TechMeme timestamps."""
    now_ts = datetime.now(timezone.utc).timestamp()
    reddit_all: list[dict] = []
    for s in SUBREDDITS:
        reddit_all.extend(all_posts.get(s["name"], []))
    hn_all = list(all_posts.get("hackernews", []))
    tm_all = list(all_posts.get("techmeme", []))

    def in_window(posts: list[dict], secs: int) -> list[dict]:
        cutoff = now_ts - secs
        return [p for p in posts if float(p.get("created_utc") or 0) >= cutoff]

    windows_sec = {"day": 86400, "week": 7 * 86400, "month": 30 * 86400}

    bundles_text_parts: list[str] = []
    merged_by_window: dict[str, list[dict]] = {}

    for key in ("day", "week", "month"):
        secs = windows_sec[key]
        hn_posts = in_window(hn_all, secs)
        rd_posts = in_window(reddit_all, secs)
        tm_posts = in_window(tm_all, secs)
        merged_by_window[key] = hn_posts + rd_posts + tm_posts

        hn_t = _titles_for_summaries(hn_posts)
        rd_t = _titles_for_summaries(rd_posts)
        tm_t = _titles_for_summaries(tm_posts)

        human = {"day": "DAY (~24 hours)", "week": "WEEK (~7 days)", "month": "MONTH (~30 days)"}[key]
        bundles_text_parts.append(
            f"{human}\nHacker News:\n"
            + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(hn_t))
            + "\n\nReddit (aggregated tech subs):\n"
            + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(rd_t))
            + "\n\nTechMeme:\n"
            + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(tm_t))
        )

    bundles_prompt = (
        "\n\n---\n\n".join(bundles_text_parts)
        + "\n\nYou write topical summaries for a fixed right-hand sidebar on a tech digest page.\n"
        "Audience: engineers skim-reading.\n\n"
        "Rules:\n"
        "- Return ONLY valid JSON with keys exactly: day, week, month.\n"
        "- Each value MUST be a JSON array of objects with keys \"topic\" and \"text\".\n"
        "- topic: short Title Case heading.\n"
        "- text: 2–4 sentences of continuous prose. Paraphrase themes; do NOT quote or closely reproduce headlines.\n"
        "- Do NOT use curly/smart quotes, markdown, or bullet characters.\n"
        "- Cluster related headlines; synthesize across Reddit, Hacker News, AND TechMeme together.\n"
        "- Include roughly 5–10 topics per window when there is enough signal; omit thin topics.\n"
        "- Neutral, understated tone.\n"
    )

    texts_obj = _openai_feed_summaries(bundles_prompt)
    if texts_obj is None:
        texts_obj = {
            k: _fallback_topic_sections(merged_by_window[k])
            for k in ("day", "week", "month")
        }

    return {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "feeds": ["Hacker News", "Reddit", "TechMeme"],
        "windows": {
            "day": "~24h by story timestamp",
            "week": "~7d",
            "month": "~30d",
        },
        "day": texts_obj["day"],
        "week": texts_obj["week"],
        "month": texts_obj["month"],
    }


def _summaries_json_for_html(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")


def build_script_block(posts_json: str, colors_json: str, summaries_json_lit: str) -> str:
    return f"""<script type="application/json" id="digest-feed-summaries-data">{summaries_json_lit}</script>
<script>
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

function top5BadgeLabel(post) {{
  if (post.source === 'hackernews') return 'Hacker News';
  if (post.source === 'techmeme') return 'TechMeme';
  return 'r/' + post.sub;
}}

function renderTop5Column(containerId, pool, timeWindow) {{
  const now = Math.floor(Date.now() / 1000);
  const slice = timeWindow === 0 ? pool : pool.filter(p => (now - p.created) <= timeWindow);
  const top5 = selectTop5(slice);
  const container = document.getElementById(containerId);
  if (!container) return;
  if (top5.length === 0) {{
    container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--muted);font-size:13px">No posts in this window.</div>';
    return;
  }}
  container.innerHTML = top5.map((post, i) => {{
    let color = SUB_COLORS[post.sub] || '#5c6bc0';
    if (post.source === 'hackernews') color = '#f59e0b';
    else if (post.source === 'techmeme') color = '#14b8a6';
    const rankColor = RANK_COLORS[i];
    const domainTag = post.domain ? `<span class="post-domain">${{esc(post.domain)}}</span>` : '';
    const lbl = top5BadgeLabel(post);
    return `
    <div class="top5-item" data-created="${{post.created}}" data-source="${{post.source}}">
      <span class="top5-rank" style="color:${{rankColor}}">${{i + 1}}</span>
      <div class="top5-body">
        <a class="top5-title" href="${{esc(post.url)}}" target="_blank" rel="noopener">${{esc(post.title)}}</a>
        <div class="top5-meta">
          <span class="top5-sub-badge" style="background:${{color}}">${{esc(lbl)}}</span>
          <span class="top5-score">&#x25B2; ${{fmtNum(post.score)}}</span>
          ${{domainTag}}
          <span>${{relTime(post.created)}}</span>
          <a class="post-comments" href="${{esc(post.permalink)}}" target="_blank" rel="noopener">&#x1F4AC; ${{fmtNum(post.comments)}}</a>
        </div>
      </div>
    </div>`;
  }}).join('');
}}

function renderTop5(timeWindow) {{
  const redditP = ALL_POSTS.filter(p => p.source === 'reddit');
  const hnP = ALL_POSTS.filter(p => p.source === 'hackernews');
  const tmP = ALL_POSTS.filter(p => p.source === 'techmeme');
  renderTop5Column('reddit-top5-items', redditP, timeWindow);
  renderTop5Column('hn-top5-items', hnP, timeWindow);
  renderTop5Column('techmeme-top5-items', tmP, timeWindow);
  applyTop5SearchFilter();
}}

function applyTop5SearchFilter() {{
  const q = document.getElementById('search').value.toLowerCase();
  document.querySelectorAll('.top5-item').forEach(item => {{
    const text = item.querySelector('.top5-title')?.textContent.toLowerCase() || '';
    item.classList.toggle('hidden', !!(q && !text.includes(q)));
  }});
}}

/** Grid cards: multi-select feed pills (toggle). None clears all; All selects every feed (click again clears). */
const selectedFeeds = new Set();

function getAllFeedFilters() {{
  return [...document.querySelectorAll('.filter-btn[data-source]')]
    .map(b => b.dataset.filter)
    .filter(Boolean);
}}

function syncNoneAllButtons() {{
  const feeds = getAllFeedFilters();
  const noneBtn = document.querySelector('.filter-btn[data-filter="none"]');
  const allBtn = document.querySelector('.filter-btn[data-filter="all"]');
  const allOn = feeds.length > 0 && feeds.every(f => selectedFeeds.has(f));
  if (noneBtn) noneBtn.classList.toggle('active', selectedFeeds.size === 0);
  if (allBtn) allBtn.classList.toggle('active', allOn);
}}

function toggleFilterDrawer() {{
  const drawer = document.getElementById('filterDrawer');
  const btn = document.getElementById('filterDrawerToggle');
  if (!drawer || !btn) return;
  drawer.classList.toggle('is-open');
  btn.setAttribute('aria-expanded', drawer.classList.contains('is-open') ? 'true' : 'false');
}}

let activeTimeWindow = 604800;
let showReddit       = true;
let showHN           = true;
let showTechMeme     = true;

function toggleSource(btn) {{
  const src = btn.dataset.src;
  const on = btn.classList.toggle('active');
  if (src === 'reddit') showReddit = on;
  else if (src === 'hackernews') showHN = on;
  else if (src === 'techmeme') showTechMeme = on;
  document.querySelectorAll('[data-source-panel="' + src + '"]').forEach(el => {{
    el.style.display = on ? '' : 'none';
  }});
  renderTop5(activeTimeWindow);
  applyFilters();
}}

function filterSubs(filter, btn) {{
  if (filter === 'none') {{
    selectedFeeds.clear();
    document.querySelectorAll('.filter-btn[data-source]').forEach(b => b.classList.remove('active'));
    syncNoneAllButtons();
    applyFilters();
    return;
  }}
  if (filter === 'all') {{
    const feeds = getAllFeedFilters();
    const allOn = feeds.length > 0 && feeds.every(f => selectedFeeds.has(f));
    if (allOn) {{
      selectedFeeds.clear();
      document.querySelectorAll('.filter-btn[data-source]').forEach(b => b.classList.remove('active'));
    }} else {{
      selectedFeeds.clear();
      feeds.forEach(f => selectedFeeds.add(f));
      document.querySelectorAll('.filter-btn[data-source]').forEach(b => b.classList.add('active'));
    }}
    syncNoneAllButtons();
    applyFilters();
    return;
  }}
  if (selectedFeeds.has(filter)) {{
    selectedFeeds.delete(filter);
    btn.classList.remove('active');
  }} else {{
    selectedFeeds.add(filter);
    btn.classList.add('active');
  }}
  syncNoneAllButtons();
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
    const src = card.getAttribute('data-source') || '';

    const items = [...card.querySelectorAll('.post-item')];

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

    const sub      = card.getAttribute('data-sub') || '';
    const subMatch = selectedFeeds.has(sub);
    const sourceOk =
      (src === 'reddit' && showReddit) ||
      (src === 'hackernews' && showHN) ||
      (src === 'techmeme' && showTechMeme);

    card.style.display = (sourceOk && subMatch && shown > 0) ? '' : 'none';
  }});

  applyTop5SearchFilter();
}}

document.addEventListener('DOMContentLoaded', () => {{
  const weekBtn = document.querySelector('.time-btn[data-window="604800"]');
  if (weekBtn) weekBtn.classList.add('active');

  initDigestRail();

  renderTop5(activeTimeWindow);
  syncNoneAllButtons();
  applyFilters();
}});

function initDigestRail() {{
  const STORAGE = 'digest-rail-period';
  let summaryData = null;
  try {{
    const el = document.getElementById('digest-feed-summaries-data');
    if (el && el.textContent.trim()) {{
      summaryData = JSON.parse(el.textContent);
    }}
  }} catch (err) {{
    console.warn('digest summaries', err);
  }}

  const bodyEl = document.getElementById('digest-rail-summary');
  const metaEl = document.getElementById('digest-rail-meta');
  const toggles = document.querySelectorAll('.digest-rail-btn[data-digest-period]');

  function setPressed(active) {{
    toggles.forEach(btn => {{
      const p = btn.getAttribute('data-digest-period');
      btn.setAttribute('aria-pressed', p === active ? 'true' : 'false');
    }});
    try {{
      localStorage.setItem(STORAGE, active);
    }} catch (e2) {{}}
  }}

  let stored = null;
  try {{
    stored = localStorage.getItem(STORAGE);
  }} catch (e3) {{}}
  let period = ['day', 'week', 'month'].includes(stored) ? stored : 'day';

  function formatTs(iso) {{
    try {{
      const d = new Date(iso);
      if (!isFinite(d.valueOf())) return '';
      const o = {{
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      }};
      return d.toLocaleString(undefined, o);
    }} catch (e4) {{
      return iso || '';
    }}
  }}

  function escapeDigestHtml(s) {{
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }}
  function digestSectionsHtml(sections) {{
    if (!Array.isArray(sections) || sections.length === 0) return '';
    return sections.map(sec => {{
      const topic = escapeDigestHtml(sec.topic || 'Topic');
      const text = escapeDigestHtml(sec.text || '').replace(/\\n/g, '<br>');
      return '<article class="digest-topic"><h3 class="digest-topic-title">' + topic + '</h3><div class="digest-topic-body">' + text + '</div></article>';
    }}).join('');
  }}

  function render() {{
    if (!bodyEl || !metaEl) return;
    let sections = summaryData ? summaryData[period] : null;
    if (typeof sections === 'string') {{
      const t = sections.trim();
      sections = t ? [{{ topic: 'Overview', text: t }}] : [];
    }}
    if (!summaryData || !Array.isArray(sections) || sections.length === 0) {{
      bodyEl.innerHTML = '';
      bodyEl.textContent = 'Digest narrative unavailable for this build.';
      bodyEl.classList.add('digest-rail-muted');
      metaEl.textContent = '';
      return;
    }}
    bodyEl.innerHTML = digestSectionsHtml(sections);
    bodyEl.classList.remove('digest-rail-muted');

    const parts = [];
    if (summaryData.generatedAt) {{
      parts.push('Updated ' + formatTs(summaryData.generatedAt));
    }}
    parts.push('Refreshes with the daily scrape; stays fixed until the next run.');
    metaEl.textContent = parts.join('. ') + '.';
  }}

  setPressed(period);
  render();

  toggles.forEach(btn => {{
    btn.addEventListener('click', () => {{
      const p = btn.getAttribute('data-digest-period');
      if (!p || p === period) return;
      period = p;
      setPressed(period);
      render();
    }});
  }});
}}

</script>"""


def build_html(all_posts: dict[str, list[dict]]) -> str:
    cards_html  = ""
    filter_btns = ""
    total_posts = 0
    all_post_data: list[dict] = []

    for sub in CARD_FEEDS:
        name  = sub["name"]
        posts = all_posts.get(name, [])
        if not posts:
            continue
        total_posts += min(len(posts), EMBED_PER_CARD)
        cards_html += build_card_html(sub, posts, EMBED_PER_CARD)
        src_esc = html.escape(sub["source"])
        filter_btns += (
            f'<button type="button" class="filter-btn" data-source="{src_esc}" '
            f'data-filter="{html.escape(name)}" '
            f'onclick="filterSubs(\'{html.escape(name)}\', this)">{html.escape(sub["label"])}</button>\n  '
        )
        src = sub["source"]
        for p in posts:
            all_post_data.append({
                "title":     p.get("title", ""),
                "score":     p.get("score", 0),
                "created":   int(p.get("created_utc", 0)),
                "url":       story_link(p),
                "permalink": comments_link(p),
                "sub":       name,
                "source":    src,
                "comments":  p.get("num_comments", 0),
                "domain":    short_domain(p.get("url", "")),
            })

    sub_colors = {c["name"]: c["color"] for c in CARD_FEEDS}
    posts_json = json.dumps(all_post_data, ensure_ascii=False)
    colors_json = json.dumps(sub_colors, ensure_ascii=False)
    generated_at = datetime.now().strftime("%b %d, %Y at %H:%M")

    summaries = build_feed_summaries(all_posts)
    summaries_lit = _summaries_json_for_html(summaries)

    script_block = build_script_block(posts_json, colors_json, summaries_lit)

    return HTML_TEMPLATE.format(
        generated_at=generated_at,
        filter_buttons=filter_btns,
        cards=cards_html,
        script_block=script_block,
        total_posts=total_posts,
    )


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Reddit + Hacker News tech digest scraper")
    parser.add_argument("--output",    default="index.html", help="Output HTML file (default: index.html)")
    parser.add_argument("--min-score", type=int, default=MIN_SCORE, help=f"Minimum post score (default: {MIN_SCORE})")
    parser.add_argument("--open",      action="store_true", help="Open the page in a browser when done")
    args = parser.parse_args()

    print("Tech digest scraper (Reddit + Hacker News + TechMeme)")
    print("=" * 40)
    print(f"Fetching Reddit ({len(SUBREDDITS)} subs)…\n")

    all_posts = fetch_all(min_score=args.min_score)

    print("\n  Hacker News (Algolia, last 30d; Firebase fallback) …", end=" ", flush=True)
    all_posts["hackernews"] = fetch_hackernews(min_score=args.min_score)
    print(f"{len(all_posts['hackernews'])} posts")

    print("\n  TechMeme (RSS) …", end=" ", flush=True)
    all_posts["techmeme"] = fetch_techmeme(min_score=args.min_score)
    print(f"{len(all_posts['techmeme'])} posts")

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
