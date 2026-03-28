#!/usr/bin/env python3
"""
Comply Scraper v3 — Crawl exhaustif BFS de l'écosystème Kiwix / Junior-Entreprises

Approche : parcourt chaque domaine en BFS, suit TOUS les liens internes
sans limite artificielle de profondeur ou de nombre de pages.

Usage:
    python scraper.py [--output ../api/data/] [--visible]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

from dotenv import load_dotenv
from playwright.sync_api import Browser, Page, Playwright, sync_playwright

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────────

KIWIX_BASE = "https://kiwix.junior-entreprises.com"
LOGIN_URL = (
    "https://identity.junior-entreprises.com/realms/JEI/protocol/openid-connect/auth"
    "?client_id=kiwi-front"
    "&redirect_uri=https%3A%2F%2Fkiwix.junior-entreprises.com%2F"
    "&response_mode=fragment&response_type=code&scope=openid"
)
LEGAL_BASE = "https://legal.junior-entreprises.com"
FORMATION_BASE = "https://kiwi-formation.junior-entreprises.com"
SERVICES_URL = "https://cnje.notion.site/La-CNJE-et-vous-6121fb53e51d425295cc26fa8367a4ea"
RSE_URL = "https://comite-rse-je.notion.site/kiwi-rse"
DOCUMENTS_ROOT = f"{KIWIX_BASE}/document/folder/1-root"

SKIP_PATTERNS = [
    "logout", "login", "signin", "signup",
    "/auth/", "/oauth/", "/token",
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".ico",
    "javascript:", "mailto:", "tel:",
    "/api/", "/static/", "/media/", "/admin/",
    "/wp-admin/", "/feed/", "/rss/",
]


# ── Utilitaires ───────────────────────────────────────────────────────────────


def clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def should_skip(url: str) -> bool:
    url_lower = url.lower()
    return any(pat in url_lower for pat in SKIP_PATTERNS)


def normalize_url(href: str, base: str) -> Optional[str]:
    if not href:
        return None
    href = href.strip()
    if href.startswith(("javascript:", "mailto:", "tel:", "#")):
        return None
    url = urljoin(base, href)
    url = url.split("#")[0].rstrip("/")
    return url if url.startswith("http") else None


def save_json(data: Any, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    n = len(data) if isinstance(data, list) else 1
    logger.info(f"  Sauvegarde: {path.name} ({n} items)")


# ── Scraper principal ─────────────────────────────────────────────────────────


class ComplyScraperV3:
    """
    Scraper exhaustif basé sur BFS.
    Pour chaque domaine, part de l'URL racine et suit TOUS les liens internes.
    """

    def __init__(self, username: str, password: str, output_dir: Path, headless: bool = True):
        self.username = username
        self.password = password
        self.output_dir = output_dir
        self.headless = headless
        self.page: Optional[Page] = None
        self.browser: Optional[Browser] = None
        self._global_visited: Set[str] = set()

    # ── Authentification ──────────────────────────────────────────────────────

    def _login(self, playwright: Playwright) -> bool:
        self.browser = playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        ctx = self.browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self.page = ctx.new_page()
        self.page.set_default_timeout(30_000)

        logger.info("Connexion SSO Kiwix...")
        self.page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
        time.sleep(2)

        self.page.fill('input[name="username"]', self.username)
        self.page.fill('input[name="password"]', self.password)
        self.page.click('input[type="submit"]')

        for _ in range(25):
            time.sleep(1)
            if "kiwix.junior-entreprises.com" in self.page.url:
                time.sleep(3)
                logger.info(f"Connecte : {self.page.url}")
                return True

        logger.error(f"Echec connexion. URL actuelle: {self.page.url}")
        return False

    # ── Extraction de contenu ─────────────────────────────────────────────────

    def _extract_title(self) -> str:
        for sel in ["h1", "[class*='title'] h1", "[class*='heading']", "h2", "title"]:
            try:
                el = self.page.query_selector(sel)
                if el:
                    t = clean(el.inner_text())
                    if t and 3 < len(t) < 300:
                        return t
            except Exception:
                pass
        return ""

    def _extract_content(self) -> str:
        """
        Extrait le contenu principal de la page.
        Essaie les sélecteurs sémantiques avant de tomber sur body entier.
        Pas de limite de taille — le RAG se charge du chunking.
        """
        for sel in [
            "article",
            "main",
            ".article-body",
            "[class*='article-content']",
            "[class*='post-content']",
            "[class*='entry-content']",
            "[class*='content-body']",
            ".prose",
            "[class*='prose']",
            ".notion-page-content",
            "[class*='page-content']",
            "[class*='page-body']",
            "[class*='main-content']",
            "[role='main']",
        ]:
            try:
                el = self.page.query_selector(sel)
                if el:
                    txt = clean(el.inner_text())
                    if len(txt) > 200:
                        return txt
            except Exception:
                pass

        # Fallback : body en excluant les éléments de navigation
        try:
            # Masquer nav/header/footer avant extraction
            self.page.evaluate("""
                () => {
                    ['nav', 'header', 'footer', '[role="navigation"]',
                     '[class*="navbar"]', '[class*="sidebar"]',
                     '[class*="breadcrumb"]', '[class*="menu"]'].forEach(sel => {
                        document.querySelectorAll(sel).forEach(el => {
                            el.setAttribute('data-hide', 'true');
                            el.style.display = 'none';
                        });
                    });
                }
            """)
            body = clean(self.page.inner_text("body"))
            # Remettre les éléments
            self.page.evaluate("""
                () => {
                    document.querySelectorAll('[data-hide="true"]').forEach(el => {
                        el.style.display = '';
                    });
                }
            """)
            return body
        except Exception:
            pass

        return ""

    def _get_internal_links(self, domain_filter: str, current_url: str,
                             exclude: Optional[List[str]] = None) -> List[str]:
        """Récupère tous les liens internes au domaine depuis la page courante."""
        links = set()
        exclude = exclude or []
        try:
            for a in self.page.query_selector_all("a[href]"):
                try:
                    href = a.get_attribute("href") or ""
                    url = normalize_url(href, current_url)
                    if not url:
                        continue
                    if domain_filter not in url:
                        continue
                    if should_skip(url):
                        continue
                    if any(exc in url for exc in exclude):
                        continue
                    links.add(url)
                except Exception:
                    pass
        except Exception:
            pass
        return list(links)

    def _detect_category(self, url: str, fallback: str) -> str:
        """Tente de détecter la catégorie depuis le breadcrumb ou l'URL."""
        try:
            for sel in [
                "[class*='breadcrumb']",
                "nav[aria-label*='bread']",
                ".breadcrumbs",
                "[class*='Breadcrumb']",
            ]:
                el = self.page.query_selector(sel)
                if el:
                    txt = clean(el.inner_text())
                    if txt:
                        parts = [p.strip() for p in re.split(r"[>/›»\|]", txt) if p.strip()]
                        if len(parts) >= 2:
                            return parts[-2]
        except Exception:
            pass

        # Depuis le chemin URL
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p and p != "index.html"]
        if len(parts) >= 2:
            cat = parts[-2].replace("-", " ").replace("_", " ")
            return cat.title()

        return fallback

    # ── BFS générique ─────────────────────────────────────────────────────────

    def _bfs_crawl(
        self,
        start_url: str,
        domain_filter: str,
        source: str,
        default_category: str,
        wait_time: float = 2.0,
        first_wait: float = 3.0,
        max_pages: int = 1000,
        exclude_patterns: Optional[List[str]] = None,
        min_content_len: int = 150,
    ) -> List[Dict]:
        """
        Crawl BFS exhaustif d'un domaine.
        Suit tous les liens internes sans limite de profondeur.

        Args:
            start_url: URL de départ
            domain_filter: Chaîne que l'URL doit contenir pour être crawlée
            source: Tag source pour les documents
            default_category: Catégorie par défaut si non détectée
            wait_time: Délai entre chaque page (secondes)
            first_wait: Délai pour la première page (chargement initial)
            max_pages: Limite de sécurité (très haute, ne devrait pas être atteinte)
            exclude_patterns: Patterns d'URL à exclure du crawl
            min_content_len: Longueur minimale du contenu pour sauvegarder la page
        """
        queue: deque = deque([start_url])
        local_visited: Set[str] = set()
        results: List[Dict] = []
        is_first = True

        while queue and len(results) < max_pages:
            url = queue.popleft()

            if url in local_visited or url in self._global_visited:
                continue
            local_visited.add(url)
            self._global_visited.add(url)

            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=25_000)
                time.sleep(first_wait if is_first else wait_time)
                is_first = False
            except Exception as e:
                logger.warning(f"  Inaccessible: {url[:80]} — {e}")
                continue

            title = self._extract_title()
            content = self._extract_content()

            if content and len(content) >= min_content_len:
                category = self._detect_category(url, default_category)
                results.append({
                    "title": title or url.split("/")[-1] or url,
                    "url": url,
                    "category": category,
                    "content": content,
                    "source": source,
                    "scraped_at": datetime.now().isoformat(),
                })
                logger.info(
                    f"  [{len(results):3d}] {(title or url)[:70]} "
                    f"({len(content):,} chars)"
                )

            # Ajouter les liens internes à la queue
            new_links = self._get_internal_links(
                domain_filter, url, exclude=exclude_patterns
            )
            for link in new_links:
                if link not in local_visited and link not in self._global_visited:
                    queue.append(link)

        logger.info(
            f"  BFS termine — {len(results)} pages sauvees, "
            f"{len(local_visited)} URLs visitees"
        )
        return results

    # ── Kiwi Légal ────────────────────────────────────────────────────────────

    def scrape_kiwi_legal(self) -> List[Dict]:
        logger.info("\n=== Kiwi Legal ===")
        results = self._bfs_crawl(
            start_url=LEGAL_BASE,
            domain_filter=LEGAL_BASE,
            source="kiwi-legal",
            default_category="Legal",
            wait_time=1.5,
            first_wait=2.0,
        )
        logger.info(f"  Total Kiwi Legal: {len(results)} articles")
        return results

    # ── Kiwi Formation ────────────────────────────────────────────────────────

    def scrape_kiwi_formation(self) -> List[Dict]:
        logger.info("\n=== Kiwi Formation ===")

        # Navigation vers Formation (auth déjà active via SSO)
        try:
            self.page.goto(FORMATION_BASE, wait_until="domcontentloaded", timeout=25_000)
            time.sleep(4)
            actual_url = self.page.url
            logger.info(f"  Formation URL apres redirect: {actual_url}")
        except Exception as e:
            logger.error(f"Formation inaccessible: {e}")
            return []

        # Déterminer le domaine réel après redirection
        parsed = urlparse(actual_url)
        domain = f"{parsed.scheme}://{parsed.netloc}"

        results = self._bfs_crawl(
            start_url=actual_url,
            domain_filter=domain,
            source="kiwi-formation",
            default_category="Formation",
            wait_time=2.0,
            first_wait=3.0,
        )
        logger.info(f"  Total Kiwi Formation: {len(results)} pages")
        return results

    # ── Notion (Services & RSE) ───────────────────────────────────────────────

    def _scrape_notion_site(
        self,
        start_url: str,
        source: str,
        default_category: str,
        notion_domain: str,
    ) -> List[Dict]:
        """
        Scrape une page Notion et toutes ses sous-pages.
        Notion nécessite plus d'attente pour le rendu JavaScript.
        """
        logger.info(f"\n=== {default_category} (Notion) ===")
        results: List[Dict] = []
        queue: deque = deque([start_url])
        local_visited: Set[str] = set()

        while queue:
            url = queue.popleft()

            if url in local_visited or url in self._global_visited:
                continue
            local_visited.add(url)
            self._global_visited.add(url)

            logger.info(f"  Notion page: {url[:80]}")

            try:
                # networkidle pour attendre le rendu JS complet de Notion
                self.page.goto(url, wait_until="networkidle", timeout=45_000)
                time.sleep(6)
            except Exception as e:
                logger.warning(f"  Notion timeout (on continue): {url[:60]} — {e}")
                try:
                    time.sleep(4)
                except Exception:
                    continue

            title = self._extract_title()
            content = self._extract_content()

            if content and len(content) > 100:
                results.append({
                    "title": title or default_category,
                    "url": url,
                    "category": default_category,
                    "content": content,
                    "source": source,
                    "scraped_at": datetime.now().isoformat(),
                })
                logger.info(f"  Sauvee: {(title or url)[:60]} ({len(content):,} chars)")

            # Trouver les sous-pages Notion
            try:
                for a in self.page.query_selector_all("a[href]"):
                    try:
                        href = a.get_attribute("href") or ""
                        sub = normalize_url(href, url)
                        if (
                            sub
                            and notion_domain in sub
                            and sub not in local_visited
                            and sub not in self._global_visited
                            and not should_skip(sub)
                        ):
                            queue.append(sub)
                    except Exception:
                        pass
            except Exception:
                pass

        logger.info(f"  Total {default_category}: {len(results)} pages")
        return results

    def scrape_kiwi_services(self) -> List[Dict]:
        return self._scrape_notion_site(
            SERVICES_URL, "kiwi-services", "Services", "notion.site"
        )

    def scrape_kiwi_rse(self) -> List[Dict]:
        return self._scrape_notion_site(
            RSE_URL, "kiwi-rse", "RSE", "notion.site"
        )

    # ── Documents CNJE ────────────────────────────────────────────────────────

    def scrape_documents_cnje(self) -> List[Dict]:
        logger.info("\n=== Documents CNJE ===")
        results = self._bfs_crawl(
            start_url=DOCUMENTS_ROOT,
            domain_filter=f"{KIWIX_BASE}/document",
            source="kiwix-documents",
            default_category="Documents CNJE",
            wait_time=2.0,
            first_wait=3.0,
        )
        logger.info(f"  Total Documents: {len(results)} pages")
        return results

    # ── Actualités ────────────────────────────────────────────────────────────

    def scrape_home_news(self) -> List[Dict]:
        logger.info("\n=== Actualites Kiwix ===")
        results = self._bfs_crawl(
            start_url=f"{KIWIX_BASE}/home",
            domain_filter=KIWIX_BASE,
            source="kiwix-home",
            default_category="Actualites",
            wait_time=2.0,
            first_wait=3.0,
            # Exclure /document/ (scrape séparé) et les autres sous-domaines
            exclude_patterns=["/document/", "/api/"],
        )
        logger.info(f"  Total Actualites: {len(results)} pages")
        return results

    # ── Point d'entrée ────────────────────────────────────────────────────────

    def run(self) -> Dict[str, int]:
        stats: Dict[str, int] = {}

        with sync_playwright() as playwright:
            if not self._login(playwright):
                raise RuntimeError("Echec de connexion Kiwix — vérifiez KIWIX_USERNAME et KIWIX_PASSWORD")

            # 1. Actualités Kiwix
            data = self.scrape_home_news()
            if data:
                save_json(data, self.output_dir / "kiwix-actualites.json")
                stats["actualites"] = len(data)

            # 2. Kiwi Légal
            data = self.scrape_kiwi_legal()
            if data:
                save_json(data, self.output_dir / "kiwi-legal.json")
                stats["legal"] = len(data)

            # 3. Kiwi Formation
            data = self.scrape_kiwi_formation()
            if data:
                save_json(data, self.output_dir / "kiwi-formation.json")
                stats["formation"] = len(data)

            # 4. Kiwi Services (Notion)
            data = self.scrape_kiwi_services()
            if data:
                save_json(data, self.output_dir / "kiwi-services.json")
                stats["services"] = len(data)

            # 5. Kiwi RSE (Notion)
            data = self.scrape_kiwi_rse()
            if data:
                save_json(data, self.output_dir / "kiwi-rse.json")
                stats["rse"] = len(data)

            # 6. Documents CNJE
            data = self.scrape_documents_cnje()
            if data:
                save_json(data, self.output_dir / "kiwix-documents.json")
                stats["documents"] = len(data)

            self.browser.close()

        return stats


# ─────────────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Comply Scraper v3 — Crawl BFS exhaustif de l'ecosysteme Kiwix"
    )
    parser.add_argument("--username", default=os.getenv("KIWIX_USERNAME", ""))
    parser.add_argument("--password", default=os.getenv("KIWIX_PASSWORD", ""))
    parser.add_argument("--output", default=os.getenv("OUTPUT_DIR", "../api/data"))
    parser.add_argument("--visible", action="store_true", help="Mode debug (non headless)")
    args = parser.parse_args()

    if not args.username or not args.password:
        parser.error(
            "Credentials manquants. Utilisez --username/--password "
            "ou les variables KIWIX_USERNAME/KIWIX_PASSWORD"
        )

    output = Path(args.output)
    scraper = ComplyScraperV3(
        username=args.username,
        password=args.password,
        output_dir=output,
        headless=not args.visible,
    )

    logger.info(f"Démarrage scraping exhaustif v3 -> {output.resolve()}")
    start = time.time()

    try:
        stats = scraper.run()
    except Exception as e:
        logger.error(f"Erreur critique: {e}")
        raise

    elapsed = time.time() - start
    total = sum(stats.values())

    logger.info(f"\n{'='*60}")
    logger.info(f"Scraping termine en {elapsed:.0f}s ({elapsed / 60:.1f} min)")
    logger.info(f"Resultats par section: {stats}")
    logger.info(f"Total: {total} pages scrapees")


if __name__ == "__main__":
    main()
