#!/usr/bin/env python3
"""Re-scrape des actualités Kiwix avec sauvegarde incrémentale."""

import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

import sys
sys.path.insert(0, str(Path(__file__).parent))
from scraper import ComplyScraperV3, save_json, KIWIX_BASE

OUTPUT = Path("../api/data/kiwix-actualites.json")


def main():
    username = os.getenv("KIWIX_USERNAME", "")
    password = os.getenv("KIWIX_PASSWORD", "")

    scraper = ComplyScraperV3(username, password, OUTPUT.parent, headless=True)

    with sync_playwright() as playwright:
        if not scraper._login(playwright):
            raise RuntimeError("Echec connexion SSO")

        # BFS avec sauvegarde incrémentale toutes les 50 pages
        data = scraper._bfs_crawl(
            start_url=f"{KIWIX_BASE}/home",
            domain_filter=KIWIX_BASE,
            source="kiwix-actualites",
            default_category="Actualites",
            wait_time=2.0,
            first_wait=3.0,
            max_pages=1500,
            exclude_patterns=["/document/", "/api/"],
            checkpoint_path=OUTPUT,
            checkpoint_every=50,
        )

        scraper.browser.close()

    # Filtre users + sauvegarde finale
    clean = [d for d in data if d.get("category") != "User"]
    logging.info(f"Total: {len(data)} → {len(clean)} apres suppression users")
    save_json(clean, OUTPUT)


if __name__ == "__main__":
    main()
