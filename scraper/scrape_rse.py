#!/usr/bin/env python3
"""
Scraper dédié Kiwi RSE — comite-rse-je.notion.site
Site Notion public (pas besoin de SSO Kiwix).
Scroll agressif + expansion sidebar pour tout récupérer.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

RSE_START = "https://comite-rse-je.notion.site/kiwi-rse"
NOTION_DOMAIN = "comite-rse-je.notion.site"
OUTPUT = Path("../api/data/kiwi-rse.json")

SKIP = [".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".css", ".js",
        "javascript:", "mailto:", "tel:", "/api/"]


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize(href: str, base: str) -> Optional[str]:
    if not href or any(s in href for s in SKIP):
        return None
    href = href.strip()
    if href.startswith(("#", "javascript:", "mailto:", "tel:")):
        return None
    url = urljoin(base, href).split("#")[0].rstrip("/")
    return url if url.startswith("http") else None


def scroll_full(page) -> None:
    """Scroll jusqu'en bas pour déclencher le lazy loading."""
    try:
        page.evaluate("""
            () => new Promise(resolve => {
                let total = 0;
                const step = () => {
                    window.scrollBy(0, 400);
                    total += 400;
                    if (total < document.body.scrollHeight) {
                        setTimeout(step, 80);
                    } else {
                        window.scrollTo(0, 0);
                        resolve();
                    }
                };
                step();
            })
        """)
        time.sleep(1)
    except Exception:
        pass


def expand_notion_sidebar(page) -> None:
    """Clique sur les éléments du sidebar Notion pour révéler les sous-pages."""
    try:
        # Cherche les toggles de sidebar Notion
        toggles = page.query_selector_all(
            "[class*='notion-sidebar'] [class*='toggle'], "
            "[class*='sidebar-item'] svg, "
            "div[role='button'][class*='nav']"
        )
        for t in toggles[:30]:
            try:
                t.click(timeout=1000)
                time.sleep(0.3)
            except Exception:
                pass
    except Exception:
        pass


def extract_content(page) -> str:
    """Extraction du contenu principal Notion."""
    # Sélecteurs Notion spécifiques
    for sel in [
        ".notion-page-content",
        "[class*='notionPage']",
        "article",
        "main",
        "[role='main']",
    ]:
        try:
            el = page.query_selector(sel)
            if el:
                txt = clean(el.inner_text())
                if len(txt) > 200:
                    return txt
        except Exception:
            pass

    # Fallback body sans nav
    try:
        page.evaluate("""
            () => {
                ['nav','header','footer','[role="navigation"]',
                 '[class*="navbar"]','[class*="sidebar"]'].forEach(s => {
                    document.querySelectorAll(s).forEach(el => {
                        el.setAttribute('data-hidden','1');
                        el.style.display='none';
                    });
                });
            }
        """)
        txt = clean(page.inner_text("body"))
        page.evaluate("""
            () => {
                document.querySelectorAll('[data-hidden="1"]').forEach(el => {
                    el.style.display='';
                });
            }
        """)
        return txt
    except Exception:
        return ""


def extract_title(page) -> str:
    for sel in ["h1", "[class*='title'] h1", "[class*='page-title']", "h2"]:
        try:
            el = page.query_selector(sel)
            if el:
                t = clean(el.inner_text())
                if 3 < len(t) < 300:
                    return t
        except Exception:
            pass
    return ""


def get_links(page, current_url: str) -> List[str]:
    links = set()
    try:
        for a in page.query_selector_all("a[href]"):
            try:
                href = a.get_attribute("href") or ""
                url = normalize(href, current_url)
                if url and NOTION_DOMAIN in url:
                    links.add(url)
            except Exception:
                pass
    except Exception:
        pass
    return list(links)


def scrape_rse() -> List[Dict]:
    results: List[Dict] = []
    visited: Set[str] = set()
    queue: deque = deque([RSE_START])

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = ctx.new_page()
        page.set_default_timeout(45_000)

        while queue:
            url = queue.popleft()
            if url in visited:
                continue
            visited.add(url)

            logger.info(f"[{len(results)+1}] {url[:80]}")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                time.sleep(10)
            except Exception as e:
                logger.warning(f"  Erreur navigation: {e}")
                continue

            # Scroll + sidebar pour révéler tout le contenu
            scroll_full(page)
            expand_notion_sidebar(page)
            time.sleep(3)
            # 2ème scroll après expansion sidebar
            scroll_full(page)
            time.sleep(2)

            title = extract_title(page)
            content = extract_content(page)

            if content and len(content) >= 150:
                results.append({
                    "title": title or "Kiwi RSE",
                    "url": url,
                    "category": "RSE",
                    "content": content,
                    "source": "kiwi-rse",
                    "scraped_at": datetime.now().isoformat(),
                })
                logger.info(f"  Sauvee: {title[:60]} ({len(content):,} chars)")
            else:
                logger.info(f"  Contenu insuffisant ({len(content)} chars), ignoree")

            # Découvrir les sous-pages
            new_links = get_links(page, url)
            added = 0
            for link in new_links:
                if link not in visited:
                    queue.append(link)
                    added += 1
            if added:
                logger.info(f"  +{added} liens trouvés")

        browser.close()

    logger.info(f"\nTotal RSE: {len(results)} pages, {len(visited)} URLs visitées")
    return results


if __name__ == "__main__":
    data = scrape_rse()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Sauvegardé: {OUTPUT} ({len(data)} articles)")
