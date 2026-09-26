"""
EduPulse India — EXPANDED Multi-Source Scraper
=========================================================
FREE DATA SOURCES (13 sources):
  1.  Reddit        — r/CATprep, r/Indian_Academia, r/MBA, r/GMAT, r/IIM (+6 more)
  2.  Pagalguy      — WordPress feed + live "Latest discussion" threads
  3.  Google News   — MBA/CAT India news (multiple query sets)
  4.  Google Trends — Daily trending India (MBA/CAT keywords)
  5.  College Portals — IIMs, XLRI, FMS, MDI, SPJIMR, ISB, IIFT etc.
  6.  Quora (DDG)   — MBA/CAT Q&A via DuckDuckGo proxy
  7.  Shiksha.com   — India's #1 education portal RSS + search
  8.  Careers360   — Education news RSS
  9.  MBA Universe  — RSS + articles on MBA prep
  10. CollegeDunia  — Forum discussions
  11. YouTube       — Video titles from MBA coaching channels (public RSS)
  12. Telegram      — 2IIM / IMS / PrepLadder / CAT 2026 channels
                      (t.me preview pages; Telethon monitor if API creds set)
  13. India News    — Education RSS: HT, TOI, NDTV, The Hindu, Indian Express

All data is deduplicated by UID (md5 hash), intent-scored (see scraper/intent.py),
and refreshed every 5 minutes.
"""

import re
import time
import random
import hashlib
import logging
import urllib.request
import urllib.parse
import urllib.error
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("edupulse.scraper")

# Intent scoring (Phase 1) — rule-based, stdlib only
try:
    from scraper.intent import score_intent
except ImportError:  # direct script execution fallback
    from intent import score_intent


def _apply_intent(item: dict) -> dict:
    """Attach intent_level + intent_score to an item (idempotent)."""
    if "intent_level" not in item or "intent_score" not in item:
        try:
            level, score = score_intent(item.get("title", ""), item.get("snippet", ""))
        except Exception:
            level, score = "low", 10
        item["intent_level"] = level
        item["intent_score"] = score
    return item

# ── User-Agent pool ──────────────────────────────────────────────
_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
]


def _ua() -> str:
    return random.choice(_UA_POOL)


# -- Scout-style 3-tier fetch chain ----------------------------------------
# Tier 1: Scrapling Fetcher   -- TLS-impersonated HTTP (fast, bypasses basic bot blocks)
# Tier 2: StealthyFetcher     -- Real camoufox browser (Cloudflare bypass)
# Tier 3: Plain urllib        -- Always-available fallback
# Gracefully degrades when Scrapling is not installed.
try:
    from scrapling.fetchers import Fetcher as _SF, StealthyFetcher as _SSF
    _SCRAPLING = True
    logger.info("[Scraper] Scrapling available -- using 3-tier fetch chain")
except Exception:
    _SF = _SSF = None
    _SCRAPLING = False
    logger.info("[Scraper] Scrapling not installed -- using urllib only")


def _fetch(url: str, timeout: int = 18, extra_headers: dict = None) -> Optional[str]:
    """3-tier HTTP fetch. Returns decoded text or None."""
    headers = {
        "User-Agent": _ua(),
        "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if extra_headers:
        headers.update(extra_headers)

    # Tier 1 -- Scrapling Fetcher (TLS impersonation, no real browser)
    if _SCRAPLING and _SF:
        try:
            page = _SF.get(url, timeout=timeout)
            if page and getattr(page, "status", 200) not in (403, 429, 503):
                text = getattr(page, "text", None) or ""
                if len(text) > 200:
                    return text
        except Exception as e:
            logger.debug("Tier1 failed %s: %s", url, e)

    # Tier 2 -- StealthyFetcher (real browser, Cloudflare bypass)
    # Skip for RSS/JSON endpoints -- use only for blocked HTML pages
    if _SCRAPLING and _SSF and not any(
        x in url for x in ["rss", ".xml", ".json", "feeds", "news.google", ".rss"]
    ):
        try:
            page = _SSF.fetch(url, headless=True, network_idle=True,
                              timeout=min(timeout * 2, 45))
            if page and getattr(page, "status", 200) not in (403, 429, 503):
                text = getattr(page, "text", None) or ""
                if len(text) > 200:
                    return text
        except Exception as e:
            logger.debug("Tier2 failed %s: %s", url, e)

    # Tier 3 -- Plain urllib (always works)
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("Fetch failed %s - %s", url, exc)
        return None




def _uid(source: str, text: str) -> str:
    return hashlib.md5(f"{source}:{text}".encode()).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_rss(xml_text: str, source_name: str) -> list[dict]:
    """Generic RSS/Atom parser. Returns list of item dicts."""
    results = []
    try:
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        # RSS 2.0
        items = root.findall(".//item")
        if not items:
            # Atom
            items = root.findall(".//atom:entry", ns)
        for item in items[:20]:
            title = (
                item.findtext("title") or
                item.findtext("atom:title", namespaces=ns) or ""
            ).strip()
            link = (
                item.findtext("link") or
                item.findtext("atom:link", namespaces=ns) or
                (item.find("atom:link", ns).get("href") if item.find("atom:link", ns) is not None else "") or ""
            ).strip()
            desc = re.sub(r"<[^>]+>", "", (
                item.findtext("description") or
                item.findtext("atom:summary", namespaces=ns) or
                item.findtext("atom:content", namespaces=ns) or ""
            )).strip()
            pub = item.findtext("pubDate") or item.findtext("atom:published", namespaces=ns) or _now_iso()
            full = (title + " " + desc).lower()
            results.append({
                "uid": _uid(source_name, title or link),
                "source": source_name,
                "title": title[:220],
                "snippet": desc[:450],
                "url": link,
                "published": pub,
                "exam_hint": _detect_exam(full),
                "city_hint": _detect_city(full),
                "scraped_at": _now_iso(),
            })
    except Exception as exc:
        logger.warning("[%s] RSS parse error: %s", source_name, exc)
    for item in results:
        _apply_intent(item)
    return results


# ═══════════════════════════════════════════════════════════════════
# SOURCE 1 — REDDIT
# ═══════════════════════════════════════════════════════════════════
REDDIT_SUBS = [
    "CATprep", "Indian_Academia", "MBA", "IIM", "GRE",
    "GMAT_prep", "StudyAbroad", "Indians", "india",
    "EngineeringStudents", "highereducation",
]
REDDIT_KEYWORDS = [
    "cat", "xat", "gmat", "mba", "iim", "coaching", "admit",
    "percentile", "score", "india", "b-school", "business school",
    "iift", "snap", "cmat", "nmat", "mat exam", "mba admission",
]

def scrape_reddit() -> list[dict]:
    """Use Reddit's public RSS feeds (not blocked like the JSON API)."""
    results = []
    for sub in REDDIT_SUBS:
        # Reddit RSS is public and not rate-limited like JSON API
        url = f"https://www.reddit.com/r/{sub}/new/.rss?limit=25"
        xml_text = _fetch(url, extra_headers={
            "Accept": "application/rss+xml, text/xml",
        })
        if not xml_text:
            # fallback: hot posts
            url = f"https://www.reddit.com/r/{sub}/.rss?limit=20"
            xml_text = _fetch(url)
        if not xml_text:
            time.sleep(0.5)
            continue
        try:
            root = ET.fromstring(xml_text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entries = root.findall(".//atom:entry", ns) or root.findall(".//item")
            for entry in entries[:15]:
                title = (
                    entry.findtext("atom:title", namespaces=ns) or
                    entry.findtext("title") or ""
                ).strip()
                link_el = entry.find("atom:link", ns)
                link = (
                    (link_el.get("href") if link_el is not None else "") or
                    entry.findtext("link") or ""
                ).strip()
                content = re.sub(r"<[^>]+>", "", (
                    entry.findtext("atom:content", namespaces=ns) or
                    entry.findtext("atom:summary", namespaces=ns) or
                    entry.findtext("description") or ""
                )).strip()
                full = (title + " " + content).lower()
                if not any(kw in full for kw in REDDIT_KEYWORDS):
                    continue
                results.append({
                    "uid": _uid("reddit", link or title),
                    "source": "reddit",
                    "subreddit": sub,
                    "title": title[:220],
                    "snippet": content[:400],
                    "url": link,
                    "exam_hint": _detect_exam(full),
                    "city_hint": _detect_city(full),
                    "scraped_at": _now_iso(),
                })
        except Exception as exc:
            logger.warning("Reddit r/%s RSS: %s", sub, exc)
        time.sleep(0.8)
    logger.info("Reddit: %d posts", len(results))
    for _it in results:
        _apply_intent(_it)
    return results


# ═══════════════════════════════════════════════════════════════════
# SOURCE 2 — PAGALGUY
# ═══════════════════════════════════════════════════════════════════
# NOTE (Phase 1 fix, 2026-09-26): the old /rss/{cat,mba,gmat,...} URLs are
# dead — they return 200KB of HTML, not RSS. Pagalguy is now WordPress;
# its real feed is https://www.pagalguy.com/feed/ (verified live).
# We also pull fresh discussion-thread titles from the homepage's
# "Latest discussion" section (high-value aspirant threads).
PAGALGUY_FEEDS = [
    "https://www.pagalguy.com/feed/",
]

def scrape_pagalguy() -> list[dict]:
    results = []
    for url in PAGALGUY_FEEDS:
        xml_text = _fetch(url, timeout=20)
        if xml_text and ("<rss" in xml_text or "<feed" in xml_text):
            items = _parse_rss(xml_text, "pagalguy")
            results.extend(items)
        time.sleep(0.7)

    # Homepage "Latest discussion" threads — real aspirant conversations
    try:
        home = _fetch("https://www.pagalguy.com/", timeout=20)
        if home:
            # Discussion thread links: /discussions/... with descriptive titles
            threads = re.findall(
                r'href="(https://www\.pagalguy\.com/discussions/[^"]+)"[^>]*>([^<]{12,180})<',
                home, re.IGNORECASE,
            )
            seen = set()
            for href, title in threads:
                title = re.sub(r'\s+', ' ', title).strip()
                if href in seen or len(title) < 12:
                    continue
                seen.add(href)
                results.append({
                    "uid": _uid("pagalguy", href),
                    "source": "pagalguy",
                    "title": title[:220],
                    "snippet": "Live discussion thread on Pagalguy — India's MBA forum",
                    "url": href,
                    "exam_hint": _detect_exam(title.lower()),
                    "city_hint": _detect_city(title.lower()),
                    "scraped_at": _now_iso(),
                })
                if len(seen) >= 15:
                    break
    except Exception as exc:
        logger.warning("Pagalguy homepage threads: %s", exc)

    logger.info("Pagalguy: %d items", len(results))
    for _it in results:
        _apply_intent(_it)
    return results


# ═══════════════════════════════════════════════════════════════════
# SOURCE 3 — GOOGLE NEWS RSS (multiple query sets)
# ═══════════════════════════════════════════════════════════════════
GOOGLE_NEWS_QUERIES = [
    "CAT exam 2025 India",
    "MBA admission India 2025",
    "IIM CAT 2025 cutoff",
    "XAT GMAT India coaching",
    "SNAP NMAT CMAT exam 2025",
    "MBA college India ranking",
    "MBA entrance exam India",
    "IIM Ahmedabad admission 2025",
    "XLRI XAT 2025",
    "MBA working professional India",
    "GMAT score India MBA",
    "MBA scholarship India",
]

def scrape_google_news() -> list[dict]:
    results = []
    for query in GOOGLE_NEWS_QUERIES:
        q = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
        xml_text = _fetch(url, timeout=20)
        if xml_text:
            items = _parse_rss(xml_text, "google_news")
            results.extend(items)
        time.sleep(0.4)
    logger.info("Google News: %d items", len(results))
    for _it in results:
        _apply_intent(_it)
    return results


# ═══════════════════════════════════════════════════════════════════
# SOURCE 4 — GOOGLE TRENDS (India daily)
# ═══════════════════════════════════════════════════════════════════
def scrape_google_trends() -> list[dict]:
    """Fetch Google Trends via the working RSS endpoint."""
    results = []
    # Use the correct 2024 endpoint
    urls_to_try = [
        "https://trends.google.com/trending/rss?geo=IN",
        "https://trends.google.co.in/trending/rss?geo=IN",
    ]
    xml_text = None
    for url in urls_to_try:
        xml_text = _fetch(url, timeout=15)
        if xml_text:
            break
    if not xml_text:
        # Fallback: scrape trending page HTML
        html = _fetch("https://trends.google.com/trends/hottrends/atom/feed?pn=p45", timeout=15)
        xml_text = html
    if not xml_text:
        logger.info("Google Trends: endpoint unavailable")
        return results
    try:
        root = ET.fromstring(xml_text)
        for item in root.findall(".//item")[:20]:
            title = (item.findtext("title") or "").strip()
            traffic = item.findtext(
                "{https://trends.google.com/trends/trendingsearches}approx_traffic"
            ) or "?"
            full = title.lower()
            if not any(k in full for k in [
                "cat", "mba", "iim", "xat", "gmat", "cmat", "mat", "exam",
                "admit", "coaching", "bschool", "nmat", "snap", "iift"
            ]):
                continue
            results.append({
                "uid": _uid("trends", title),
                "source": "google_trends",
                "title": title,
                "snippet": f"Approx daily searches in India: {traffic}",
                "url": f"https://trends.google.com/trends/explore?q={urllib.parse.quote(title)}&geo=IN",
                "exam_hint": _detect_exam(full),
                "city_hint": None,
                "scraped_at": _now_iso(),
            })
    except Exception as exc:
        logger.warning("Google Trends: %s", exc)
    logger.info("Google Trends: %d items", len(results))
    for _it in results:
        _apply_intent(_it)
    return results


# ═══════════════════════════════════════════════════════════════════
# SOURCE 5 — COLLEGE PORTALS (curated + scraped deadlines)
# ═══════════════════════════════════════════════════════════════════
COLLEGES = [
    {"name": "IIM Ahmedabad", "url": "https://www.iima.ac.in/pgp/admission", "exam": "CAT", "tier": "Tier-1", "city": "Ahmedabad"},
    {"name": "IIM Bangalore", "url": "https://www.iimb.ac.in/programs/full-time-programmes/post-graduate-programme", "exam": "CAT", "tier": "Tier-1", "city": "Bangalore"},
    {"name": "IIM Calcutta", "url": "https://www.iimcal.ac.in/programmes/mba", "exam": "CAT", "tier": "Tier-1", "city": "Kolkata"},
    {"name": "IIM Lucknow", "url": "https://www.iiml.ac.in/programmes/pgsm.html", "exam": "CAT", "tier": "Tier-1", "city": "Lucknow"},
    {"name": "IIM Kozhikode", "url": "https://www.iimk.ac.in/academics/pgp/", "exam": "CAT", "tier": "Tier-1", "city": "Kozhikode"},
    {"name": "IIM Indore", "url": "https://www.iimidr.ac.in/programmes/pgp/", "exam": "CAT", "tier": "Tier-1", "city": "Indore"},
    {"name": "XLRI Jamshedpur", "url": "https://www.xlri.ac.in/programmes/pgdm-bm/", "exam": "XAT", "tier": "Tier-1", "city": "Jamshedpur"},
    {"name": "FMS Delhi", "url": "http://www.fms.edu/admissions.aspx", "exam": "CAT", "tier": "Tier-1", "city": "Delhi"},
    {"name": "MDI Gurgaon", "url": "https://www.mdi.ac.in/programmes/pgpm/", "exam": "CAT", "tier": "Tier-2", "city": "Gurgaon"},
    {"name": "SPJIMR Mumbai", "url": "https://www.spjimr.org/programme/pgdm/", "exam": "CAT/GMAT", "tier": "Tier-1", "city": "Mumbai"},
    {"name": "ISB Hyderabad", "url": "https://www.isb.edu/en/programmes/MBA.html", "exam": "GMAT/GRE", "tier": "Tier-1", "city": "Hyderabad"},
    {"name": "IIFT Delhi", "url": "https://www.iift.ac.in/iift/index.cfm", "exam": "IIFT/CAT", "tier": "Tier-1", "city": "Delhi"},
    {"name": "TISS Mumbai", "url": "https://www.tiss.edu/view/6/admissions/", "exam": "TISS-NET", "tier": "Tier-2", "city": "Mumbai"},
    {"name": "NMIMS Mumbai", "url": "https://www.nmims.edu/schools-and-departments/sbm/", "exam": "NMAT", "tier": "Tier-2", "city": "Mumbai"},
    {"name": "Symbiosis Pune", "url": "https://www.sibmpune.edu.in/", "exam": "SNAP", "tier": "Tier-2", "city": "Pune"},
    {"name": "Great Lakes Chennai", "url": "https://www.greatlakes.edu.in/pgpm/", "exam": "CAT/GMAT", "tier": "Tier-2", "city": "Chennai"},
    {"name": "XIMB Bhubaneswar", "url": "https://www.ximb.ac.in/programmes/mba-business-management/", "exam": "XAT/CAT", "tier": "Tier-2", "city": "Bhubaneswar"},
    {"name": "Amity Noida", "url": "https://www.amity.edu/asm/", "exam": "CAT/MAT", "tier": "Tier-3", "city": "Noida"},
    {"name": "IMT Ghaziabad", "url": "https://www.imt.edu/pgdm/", "exam": "CAT/XAT/GMAT", "tier": "Tier-2", "city": "Ghaziabad"},
    {"name": "FORE Delhi", "url": "https://www.fsm.ac.in/pgdm.html", "exam": "CAT/XAT", "tier": "Tier-2", "city": "Delhi"},
]

def scrape_college_portals() -> list[dict]:
    results = []
    for college in COLLEGES:
        item = {
            "uid": _uid("college", college["name"]),
            "source": "college_portal",
            "title": f"{college['name']} — {college['exam']} Admissions",
            "college": college["name"],
            "exam": college["exam"],
            "tier": college["tier"],
            "city_hint": college.get("city"),
            "url": college["url"],
            "snippet": f"{college['tier']} B-School | Entry via {college['exam']} | Location: {college.get('city','')}",
            "exam_hint": _detect_exam(college["exam"].lower()),
            "scraped_at": _now_iso(),
        }
        # Try to scrape live deadline
        html = _fetch(college["url"], timeout=12)
        if html:
            dates = re.findall(
                r'(\d{1,2}[\s\-/]+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s\-/]+202\d)',
                html, re.IGNORECASE
            )
            if dates:
                item["snippet"] += f" | Deadline hint: {dates[0]}"
        results.append(item)
        time.sleep(0.8)
    logger.info("College portals: %d records", len(results))
    for _it in results:
        _apply_intent(_it)
    return results


# ═══════════════════════════════════════════════════════════════════
# SOURCE 6 — QUORA (via DuckDuckGo HTML search)
# ═══════════════════════════════════════════════════════════════════
QUORA_QUERIES = [
    "site:quora.com CAT 2025 India preparation",
    "site:quora.com MBA admission India 2025",
    "site:quora.com XAT GMAT coaching India",
    "site:quora.com IIM admission criteria India",
    "site:quora.com MBA college India which is best",
]

def scrape_quora_via_ddg() -> list[dict]:
    results = []
    for query in QUORA_QUERIES:
        q = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={q}&kl=in-en"
        html = _fetch(url, timeout=20)
        if not html:
            continue
        links = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)<', html)
        for href, text in links[:6]:
            m = re.search(r"uddg=([^&]+)", href)
            real_url = urllib.parse.unquote(m.group(1)) if m else href
            if "quora.com" not in real_url:
                continue
            results.append({
                "uid": _uid("quora", real_url),
                "source": "quora",
                "title": text.strip()[:220],
                "snippet": "",
                "url": real_url,
                "exam_hint": _detect_exam((query + text).lower()),
                "city_hint": _detect_city(text.lower()),
                "scraped_at": _now_iso(),
            })
        time.sleep(1.2)
    logger.info("Quora/DDG: %d items", len(results))
    for _it in results:
        _apply_intent(_it)
    return results


# ═══════════════════════════════════════════════════════════════════
# SOURCE 7 — SHIKSHA.COM (India's #1 education portal)
# ═══════════════════════════════════════════════════════════════════
SHIKSHA_FEEDS = [
    "https://www.shiksha.com/mba/news?format=rss",
    "https://www.shiksha.com/mba/articles?format=rss",
    "https://news.google.com/rss/search?q=site:shiksha.com+MBA+CAT+India&hl=en-IN&gl=IN&ceid=IN:en",
]
SHIKSHA_PAGES = [
    "https://www.shiksha.com/mba/cat-exam",
    "https://www.shiksha.com/mba/xat-exam",
    "https://www.shiksha.com/mba/gmat",
    "https://www.shiksha.com/mba/top-mba-colleges-india",
]

def scrape_shiksha() -> list[dict]:
    results = []
    # Try RSS feeds
    for url in SHIKSHA_FEEDS:
        xml_text = _fetch(url, timeout=18)
        if xml_text and ("<rss" in xml_text or "<feed" in xml_text):
            results.extend(_parse_rss(xml_text, "shiksha"))
        time.sleep(0.5)
    # HTML pages for article listings
    for page_url in SHIKSHA_PAGES:
        html = _fetch(page_url, timeout=18)
        if not html:
            continue
        # Extract article/exam titles and links
        links = re.findall(
            r'href="(https://www\.shiksha\.com[^"]+(?:exam|article|college|mba|cat|xat|gmat)[^"]*)"[^>]*>([^<]{15,200})<',
            html, re.IGNORECASE
        )
        for href, text in links[:8]:
            text = re.sub(r'\s+', ' ', text).strip()
            if len(text) < 10:
                continue
            results.append({
                "uid": _uid("shiksha", href),
                "source": "shiksha",
                "title": text[:220],
                "snippet": f"From Shiksha.com — India's top education portal",
                "url": href,
                "exam_hint": _detect_exam((text + href).lower()),
                "city_hint": _detect_city(text.lower()),
                "scraped_at": _now_iso(),
            })
        time.sleep(0.8)
    logger.info("Shiksha: %d items", len(results))
    for _it in results:
        _apply_intent(_it)
    return results


# ═══════════════════════════════════════════════════════════════════
# SOURCE 8 — CAREERS360
# ═══════════════════════════════════════════════════════════════════
CAREERS360_FEEDS = [
    "https://news.google.com/rss/search?q=site:careers360.com+MBA+CAT&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=site:careers360.com+IIM+admission&hl=en-IN&gl=IN&ceid=IN:en",
]
CAREERS360_PAGES = [
    "https://www.careers360.com/mba/cat-exam",
    "https://www.careers360.com/mba",
]

def scrape_careers360() -> list[dict]:
    results = []
    for url in CAREERS360_FEEDS:
        xml_text = _fetch(url, timeout=18)
        if xml_text and "<rss" in xml_text:
            results.extend(_parse_rss(xml_text, "careers360"))
        time.sleep(0.5)
    for page_url in CAREERS360_PAGES:
        html = _fetch(page_url, timeout=18)
        if not html:
            continue
        links = re.findall(
            r'href="(https://www\.careers360\.com[^"]*(?:mba|cat|xat|gmat|iim|exam|college)[^"]*)"[^>]*>([^<]{15,200})<',
            html, re.IGNORECASE
        )
        for href, text in links[:8]:
            text = re.sub(r'\s+', ' ', text).strip()
            if len(text) < 10:
                continue
            results.append({
                "uid": _uid("careers360", href),
                "source": "careers360",
                "title": text[:220],
                "snippet": "From Careers360 — India's education & career platform",
                "url": href,
                "exam_hint": _detect_exam((text + href).lower()),
                "city_hint": _detect_city(text.lower()),
                "scraped_at": _now_iso(),
            })
        time.sleep(0.6)
    logger.info("Careers360: %d items", len(results))
    for _it in results:
        _apply_intent(_it)
    return results


# ═══════════════════════════════════════════════════════════════════
# SOURCE 9 — MBA UNIVERSE
# ═══════════════════════════════════════════════════════════════════
MBA_UNIVERSE_FEEDS = [
    "https://news.google.com/rss/search?q=site:mbauniverse.com&hl=en-IN&gl=IN&ceid=IN:en",
]
MBA_UNIVERSE_PAGES = [
    "https://www.mbauniverse.com/cat",
    "https://www.mbauniverse.com/articles",
    "https://www.mbauniverse.com/mba-colleges",
]

def scrape_mba_universe() -> list[dict]:
    results = []
    for url in MBA_UNIVERSE_FEEDS:
        xml_text = _fetch(url, timeout=18)
        if xml_text and "<rss" in xml_text:
            results.extend(_parse_rss(xml_text, "mba_universe"))
        time.sleep(0.5)
    for page_url in MBA_UNIVERSE_PAGES:
        html = _fetch(page_url, timeout=18)
        if not html:
            continue
        # Article titles
        links = re.findall(
            r'href="([^"]*(?:cat|xat|mba|gmat|iim|exam|college|admission)[^"]*)"[^>]*>([^<]{15,200})<',
            html, re.IGNORECASE
        )
        for href, text in links[:6]:
            text = re.sub(r'\s+', ' ', text).strip()
            if len(text) < 10:
                continue
            full_url = href if href.startswith("http") else "https://www.mbauniverse.com" + href
            results.append({
                "uid": _uid("mba_universe", full_url),
                "source": "mba_universe",
                "title": text[:220],
                "snippet": "From MBAUniverse.com",
                "url": full_url,
                "exam_hint": _detect_exam((text + href).lower()),
                "city_hint": _detect_city(text.lower()),
                "scraped_at": _now_iso(),
            })
        time.sleep(0.8)
    logger.info("MBA Universe: %d items", len(results))
    for _it in results:
        _apply_intent(_it)
    return results


# ═══════════════════════════════════════════════════════════════════
# SOURCE 10 — COLLEGEDUNIA (India's largest college discovery portal)
# ═══════════════════════════════════════════════════════════════════
COLLEGEDUNIA_PAGES = [
    "https://collegedunia.com/mba",
    "https://collegedunia.com/mba/cat-accepting-colleges",
    "https://collegedunia.com/mba/xat-accepting-colleges",
    "https://collegedunia.com/mba/gmat-accepting-colleges",
]

def scrape_collegedunia() -> list[dict]:
    results = []
    for page_url in COLLEGEDUNIA_PAGES:
        html = _fetch(page_url, timeout=18)
        if not html:
            continue
        # College names and links
        links = re.findall(
            r'href="(https://collegedunia\.com[^"]*(?:mba|college|iim|business)[^"]*)"[^>]*>([^<]{10,150})<',
            html, re.IGNORECASE
        )
        for href, text in links[:10]:
            text = re.sub(r'\s+', ' ', text).strip()
            if len(text) < 8:
                continue
            results.append({
                "uid": _uid("collegedunia", href),
                "source": "collegedunia",
                "title": text[:220],
                "snippet": "From CollegeDunia — India's largest college discovery platform",
                "url": href,
                "exam_hint": _detect_exam((text + page_url).lower()),
                "city_hint": _detect_city(text.lower()),
                "scraped_at": _now_iso(),
            })
        time.sleep(0.7)
    logger.info("CollegeDunia: %d items", len(results))
    for _it in results:
        _apply_intent(_it)
    return results


# ═══════════════════════════════════════════════════════════════════
# SOURCE 11 — YOUTUBE RSS (Public channel video feeds — no API needed)
# ═══════════════════════════════════════════════════════════════════
# YouTube public RSS feed via channel ID (no API key needed)
YOUTUBE_CHANNEL_IDS = [
    "UCVhBCd3VEbYpMeNi1uPiRaQ",  # Career Launcher
    "UCj99xKJHGlQZhBJDGNiNbkQ",  # IMS India
    "UCKmcMSQHpDhEuKl22eioozw",  # 2IIM CAT prep
    "UC9-y-6csu5WGm29I7JiwpnA",  # Computerphile (generic fallback)
    "UCz9UrBKuWV3oXTf-FDaOtqg",  # TIME Institute (CAT coaching)
    "UCM0eQHMsYFhyBVbvnHqFmkA",  # Bulls Eye CAT
]

def scrape_youtube_rss() -> list[dict]:
    results = []
    for channel_id in YOUTUBE_CHANNEL_IDS:
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        xml_text = _fetch(url, timeout=15)
        if not xml_text:
            continue
        try:
            root = ET.fromstring(xml_text)
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "media": "http://search.yahoo.com/mrss/",
                "yt": "http://www.youtube.com/xml/schemas/2015",
            }
            entries = root.findall("atom:entry", ns)
            channel_name = (root.findtext("atom:title", namespaces=ns) or channel_id).strip()
            for entry in entries[:8]:
                title = (entry.findtext("atom:title", namespaces=ns) or "").strip()
                vid_url = ""
                link_el = entry.find("atom:link", ns)
                if link_el is not None:
                    vid_url = link_el.get("href", "")
                desc_el = entry.find("media:group/media:description", ns)
                desc = (desc_el.text or "").strip() if desc_el is not None else ""
                published = entry.findtext("atom:published", namespaces=ns) or _now_iso()
                full = (title + " " + desc).lower()
                if not any(k in full for k in [
                    "cat", "mba", "iim", "xat", "gmat", "cmat", "coaching",
                    "exam", "admission", "percentile", "bschool", "b-school",
                ]):
                    continue
                results.append({
                    "uid": _uid("youtube", vid_url or title),
                    "source": "youtube",
                    "title": title[:220],
                    "snippet": desc[:300],
                    "url": vid_url,
                    "channel": channel_name,
                    "published": published,
                    "exam_hint": _detect_exam(full),
                    "city_hint": _detect_city(full),
                    "scraped_at": _now_iso(),
                })
        except Exception as exc:
            logger.warning("YouTube RSS %s: %s", channel_id, exc)
        time.sleep(0.5)
    logger.info("YouTube: %d items", len(results))
    for _it in results:
        _apply_intent(_it)
    return results


# ═══════════════════════════════════════════════════════════════════
# SOURCE 12 — TELEGRAM PUBLIC CHANNELS (via t.me preview pages)
# ═══════════════════════════════════════════════════════════════════
# NOTE (Phase 1 fix, 2026-09-26): the previous channel list was dead —
# all 8 handles returned empty preview shells ("Contact @..." pages).
# These 4 were verified live on 2026-09-26 via t.me/s/ preview HTML
# (each returned 20 message wraps):
TELEGRAM_CHANNELS = [
    "twoiim",        # 2IIM CAT Preparation (channel)
    "imscat25prep",  # IMS CAT Preparation (channel)
    "CATPrepLadder", # PrepLadder CAT (channel)
    "cat_2026_iim",  # CAT 2026 aspirant community
]

# Optional upgrade: Telethon-based monitoring (needs API credentials).
# Get them free at https://my.telegram.org -> "API development tools".
# Set TELEGRAM_API_ID and TELEGRAM_API_HASH env vars to activate.
# Telethon reads full message history (not just the 20 preview posts)
# and can also list group members for the DM funnel (Phase 2).
try:
    from telethon import TelegramClient as _TgClient  # type: ignore
    _TELETHON = True
except Exception:
    _TgClient = None
    _TELETHON = False


def _scrape_telegram_telethon(max_per_channel: int = 30) -> list[dict]:
    """Telethon monitor — only runs when API creds are configured."""
    import os
    import asyncio
    api_id = os.getenv("TELEGRAM_API_ID", "")
    api_hash = os.getenv("TELEGRAM_API_HASH", "")
    if not (_TELETHON and api_id and api_hash):
        return []

    results = []

    async def _run():
        client = _TgClient("edupulse_tg", int(api_id), api_hash)
        await client.start()
        try:
            for channel in TELEGRAM_CHANNELS:
                try:
                    msgs = await client.get_messages(channel, limit=max_per_channel)
                    for m in msgs:
                        text = (m.text or "").strip()
                        if len(text) < 20:
                            continue
                        full = text.lower()
                        if not any(k in full for k in [
                            "cat", "mba", "iim", "xat", "gmat", "exam", "coaching",
                            "percentile", "admission", "bschool",
                        ]):
                            continue
                        results.append({
                            "uid": _uid("telegram", f"{channel}:{m.id}"),
                            "source": "telegram",
                            "channel": f"@{channel}",
                            "title": text[:120] + ("..." if len(text) > 120 else ""),
                            "snippet": text[:300],
                            "url": f"https://t.me/{channel}/{m.id}",
                            "exam_hint": _detect_exam(full),
                            "city_hint": _detect_city(full),
                            "scraped_at": _now_iso(),
                        })
                except Exception as exc:
                    logger.warning("Telethon @%s: %s", channel, exc)
                await asyncio.sleep(1)
        finally:
            await client.disconnect()

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.warning("Telethon monitor failed: %s", exc)
    logger.info("Telegram (telethon): %d items", len(results))
    for _it in results:
        _apply_intent(_it)
    return results


def scrape_telegram_public() -> list[dict]:
    # Prefer Telethon when credentials are configured (full history).
    tg_items = _scrape_telegram_telethon()
    if tg_items:
        return tg_items

    # Fallback: t.me/s/ preview pages (last ~20 posts, no login needed).
    import html as _html_mod
    results = []
    for channel in TELEGRAM_CHANNELS:
        url = f"https://t.me/s/{channel}"
        html = _fetch(url, timeout=15)
        if not html:
            continue
        try:
            # Extract message texts from Telegram preview page
            messages = re.findall(
                r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
                html, re.DOTALL
            )
            for msg_html in messages[:10]:
                text = re.sub(r'<[^>]+>', '', msg_html).strip()
                text = _html_mod.unescape(text)  # decode &#33; &#39; &quot; etc.
                text = re.sub(r'\s+', ' ', text)
                if len(text) < 20:
                    continue
                full = text.lower()
                if not any(k in full for k in [
                    "cat", "mba", "iim", "xat", "gmat", "exam", "coaching",
                    "percentile", "admission", "bschool",
                ]):
                    continue
                results.append({
                    "uid": _uid("telegram", text[:100]),
                    "source": "telegram",
                    "channel": f"@{channel}",
                    "title": text[:120] + ("..." if len(text) > 120 else ""),
                    "snippet": text[:300],
                    "url": f"https://t.me/{channel}",
                    "exam_hint": _detect_exam(full),
                    "city_hint": _detect_city(full),
                    "scraped_at": _now_iso(),
                })
        except Exception as exc:
            logger.warning("Telegram @%s: %s", channel, exc)
        time.sleep(0.8)
    logger.info("Telegram: %d items", len(results))
    for _it in results:
        _apply_intent(_it)
    return results


# ═══════════════════════════════════════════════════════════════════
# SOURCE 13 — INDIA-SPECIFIC EDUCATION NEWS RSS (Hindustan Times, TOI, NDTV)
# ═══════════════════════════════════════════════════════════════════
INDIA_NEWS_FEEDS = [
    "https://www.hindustantimes.com/rss/education/rssfeed.xml",
    "https://timesofindia.indiatimes.com/rss.cms?msid=913168",  # TOI Education
    "https://www.ndtv.com/rss/education",
    "https://www.thehindu.com/education/?service=rss",
    "https://www.financialexpress.com/education/feed/",
    "https://indianexpress.com/section/education/feed/",
]

def scrape_india_news() -> list[dict]:
    results = []
    for feed_url in INDIA_NEWS_FEEDS:
        xml_text = _fetch(feed_url, timeout=18)
        if not xml_text:
            continue
        items = _parse_rss(xml_text, "india_news")
        # Filter for MBA/CAT relevance
        for item in items:
            full = (item.get("title", "") + " " + item.get("snippet", "")).lower()
            if any(k in full for k in [
                "cat", "mba", "iim", "xat", "gmat", "cmat", "nmat",
                "snap", "mat exam", "b-school", "business school", "admission"
            ]):
                results.append(item)
        time.sleep(0.4)
    logger.info("India News: %d relevant items", len(results))
    for _it in results:
        _apply_intent(_it)
    return results


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════
EXAM_PATTERNS = {
    "CAT": ["cat 20", "cat exam", "cat 2", "common admission test", "iim cat", "cat prep", "cat score", "cat percentile"],
    "XAT": ["xat 20", "xat exam", "xat 2", "xavier", "xat score"],
    "GMAT": ["gmat", "graduate management"],
    "GRE": ["gre exam", "gre score", "gre prep"],
    "CMAT": ["cmat", "common management"],
    "MAT": [" mat exam", "mat 20", "management aptitude"],
    "SNAP": ["snap exam", "snap 20", "symbiosis national"],
    "NMAT": ["nmat", "nmims management"],
    "IIFT": ["iift", "indian institute of foreign"],
}

INDIA_CITIES = [
    "delhi", "mumbai", "bangalore", "bengaluru", "hyderabad", "pune", "chennai",
    "kolkata", "ahmedabad", "surat", "jaipur", "lucknow", "kanpur", "nagpur",
    "indore", "thane", "bhopal", "patna", "vadodara", "ghaziabad", "noida",
    "gurgaon", "chandigarh", "coimbatore", "kochi", "cochin", "vizag",
    "visakhapatnam", "bhubaneswar", "mysore", "mysuru", "dehradun", "amritsar",
    "ranchi", "guwahati", "jamshedpur", "raipur", "faridabad", "meerut",
    "agra", "varanasi", "allahabad", "prayagraj", "srinagar", "jammu",
    "shimla", "manali", "trichy", "tiruchirappalli", "madurai", "mangalore",
]

def _detect_exam(text: str) -> Optional[str]:
    text = text.lower()
    for exam, patterns in EXAM_PATTERNS.items():
        if any(p in text for p in patterns):
            return exam
    # Fallback: simple keyword
    for exam in ["CAT", "XAT", "GMAT", "CMAT", "SNAP", "NMAT", "MAT", "GRE", "IIFT"]:
        if exam.lower() in text:
            return exam
    return None

def _detect_city(text: str) -> Optional[str]:
    text = text.lower()
    for city in INDIA_CITIES:
        if city in text:
            return city.title()
    return None


# ═══════════════════════════════════════════════════════════════════
# MASTER SCRAPE FUNCTION
# ═══════════════════════════════════════════════════════════════════
ALL_SCRAPERS = [
    ("reddit",          scrape_reddit),
    ("pagalguy",        scrape_pagalguy),
    ("google_news",     scrape_google_news),
    ("google_trends",   scrape_google_trends),
    ("college_portals", scrape_college_portals),
    ("quora",           scrape_quora_via_ddg),
    ("shiksha",         scrape_shiksha),
    ("careers360",      scrape_careers360),
    ("mba_universe",    scrape_mba_universe),
    ("collegedunia",    scrape_collegedunia),
    ("youtube",         scrape_youtube_rss),
    ("telegram",        scrape_telegram_public),
    ("india_news",      scrape_india_news),
]


def run_all_scrapers(health_callback=None) -> list[dict]:
    """Run all 13 scrapers, return de-duplicated results.

    health_callback(name, ok, items, error) is called per source when given —
    scheduler.py / service.py pass database.record_source_health here.
    """
    all_items = []
    seen_uids = set()

    for name, fn in ALL_SCRAPERS:
        try:
            logger.info("[Scraper] Running: %s", name)
            items = fn()
            new_count = 0
            for item in items:
                uid = item.get("uid", "")
                if uid and uid not in seen_uids:
                    seen_uids.add(uid)
                    _apply_intent(item)  # safety net: every item gets scored
                    all_items.append(item)
                    new_count += 1
            logger.info("[Scraper] %s → %d new items", name, new_count)
            if health_callback:
                health_callback(name, True, new_count, None)
        except Exception as exc:
            logger.error("[Scraper] %s FAILED: %s", name, exc)
            if health_callback:
                health_callback(name, False, 0, str(exc)[:200])

    logger.info("[Scraper] Total unique items: %d", len(all_items))
    return all_items


def get_source_list() -> list[dict]:
    """Return metadata about all sources for the admin UI."""
    return [
        {"key": "reddit",          "label": "Reddit India",       "icon": "🔴", "desc": "r/CATprep, r/Indian_Academia, r/MBA, r/IIM + 7 more"},
        {"key": "pagalguy",        "label": "Pagalguy",           "icon": "💬", "desc": "MBA forum feed + live discussion threads"},
        {"key": "google_news",     "label": "Google News",        "icon": "📰", "desc": "12 MBA/CAT query sets, India geo-targeted"},
        {"key": "google_trends",   "label": "Google Trends",      "icon": "📈", "desc": "Daily trending India searches"},
        {"key": "college_portal",  "label": "College Portals",    "icon": "🏛️", "desc": "20 B-schools: IIMs, XLRI, FMS, ISB, SPJIMR..."},
        {"key": "quora",           "label": "Quora (via DDG)",    "icon": "❓", "desc": "5 MBA/CAT Q&A query sets"},
        {"key": "shiksha",         "label": "Shiksha.com",        "icon": "🎓", "desc": "India's #1 education portal"},
        {"key": "careers360",      "label": "Careers360",         "icon": "🚀", "desc": "India's education & career platform"},
        {"key": "mba_universe",    "label": "MBA Universe",       "icon": "🌐", "desc": "MBA-focused news & college data"},
        {"key": "collegedunia",    "label": "CollegeDunia",       "icon": "🏫", "desc": "India's largest college discovery portal"},
        {"key": "youtube",         "label": "YouTube RSS",        "icon": "▶️", "desc": "CAT coaching channels: 2IIM, CL, IMS, TIME"},
        {"key": "telegram",        "label": "Telegram Channels",  "icon": "✈️", "desc": "2IIM, IMS, PrepLadder, CAT 2026 channels (+Telethon if configured)"},
        {"key": "india_news",      "label": "India News RSS",     "icon": "🗞️", "desc": "HT, TOI, NDTV, The Hindu, Indian Express"},
    ]


if __name__ == "__main__":
    import os
    import sys
    # Add parent directory to path so database and other modules resolve
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )

    print("\n" + "=" * 65)
    print("  EduPulse India -- Multi-Source MBA Aspirant Lead Scraper")
    print("  Running full scrape across 13 Indian education sources...")
    print("=" * 65 + "\n")

    start_time = time.time()
    scraped_items = run_all_scrapers()
    elapsed = round(time.time() - start_time, 2)

    # Persist to database if database module is available
    added_to_db = 0
    try:
        import database as db
        db.init_db()
        added_to_db = db.save_intelligence_batch(scraped_items)
        db.log_scrape_run(added_to_db, elapsed)
    except Exception as db_err:
        logger.warning("Could not persist to DB: %s", db_err)

    # Print summary report
    print("\n" + "=" * 65)
    print(f"  SCRAPE CYCLE COMPLETE in {elapsed}s")
    print(f"  Total items collected: {len(scraped_items)}")
    print(f"  New items saved to DB: {added_to_db}")
    print("=" * 65)

    # Breakdown by Source
    by_src = {}
    by_intent = {}
    by_exam = {}
    for it in scraped_items:
        s = it.get("source", "unknown")
        by_src[s] = by_src.get(s, 0) + 1
        lvl = it.get("intent_level", "unclassified")
        by_intent[lvl] = by_intent.get(lvl, 0) + 1
        ex = it.get("exam_hint", "General")
        by_exam[ex] = by_exam.get(ex, 0) + 1

    print("\nBreakdown by Source:")
    for src, count in sorted(by_src.items(), key=lambda x: x[1], reverse=True):
        print(f"  • {src.ljust(18)}: {count}")

    print("\nBreakdown by Intent Level:")
    for lvl, count in sorted(by_intent.items(), key=lambda x: x[1], reverse=True):
        print(f"  • {lvl.ljust(18)}: {count}")

    print("\nBreakdown by Target Exam:")
    for ex, count in sorted(by_exam.items(), key=lambda x: x[1], reverse=True):
        print(f"  • {str(ex).ljust(18)}: {count}")

    print("\nSample high-intent leads:")
    high_intent = [i for i in scraped_items if i.get("intent_level") == "high"][:3]
    for h in high_intent:
        print(f"  [{h.get('source')}] {h.get('title')[:70]}... (Score: {h.get('intent_score', 0)})")
    print("=" * 65 + "\n")

