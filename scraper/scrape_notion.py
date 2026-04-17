"""
Comply — Scraper Notion (CLI standalone)
Utilise le même connecteur que l'API mais peut être lancé indépendamment.

Usage :
  python scrape_notion.py                       # → ../api/data/notion.json
  python scrape_notion.py ./output/notion.json  # chemin custom

Prérequis .env :
  NOTION_API_KEY=secret_...
  NOTION_PAGE_IDS=id1,id2   (optionnel — vide = toutes les pages)
  NOTION_DATABASE_IDS=id1   (optionnel)
"""

import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

# Importer le connecteur partagé (dans api/)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from connector_notion import sync_notion_to_json  # noqa: E402

if __name__ == "__main__":
    api_key = os.getenv("NOTION_API_KEY", "")
    if not api_key:
        print("Erreur : NOTION_API_KEY non définie dans .env")
        sys.exit(1)

    output = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "..", "api", "data", "notion.json"
    )

    print(f"Synchronisation Notion → {output}")
    count = sync_notion_to_json(api_key, output)
    print(f"Terminé : {count} pages exportées")
