"""
Comply — Scraper Google Drive (CLI standalone)
Utilise le même connecteur que l'API mais peut être lancé indépendamment.

Usage :
  python scrape_drive.py                       # → ../api/data/drive.json
  python scrape_drive.py ./output/drive.json   # chemin custom

Prérequis .env :
  # Option 1 — Compte de service
  GOOGLE_DRIVE_SERVICE_ACCOUNT='{"type":"service_account",...}'

  # Option 2 — OAuth token
  GOOGLE_DRIVE_TOKEN_FILE=./drive_token.json

  # Optionnel
  GOOGLE_DRIVE_FOLDER_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs
  GOOGLE_DRIVE_SHARED_DRIVE_ID=
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

from connector_drive import sync_drive_to_json  # noqa: E402

if __name__ == "__main__":
    sa = os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT", "")
    token = os.getenv("GOOGLE_DRIVE_TOKEN_FILE", "")
    folder = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
    shared = os.getenv("GOOGLE_DRIVE_SHARED_DRIVE_ID", "")

    if not sa and not (token and os.path.exists(token)):
        print(
            "Erreur : credentials Google Drive manquantes.\n"
            "Configurez GOOGLE_DRIVE_SERVICE_ACCOUNT ou GOOGLE_DRIVE_TOKEN_FILE dans .env"
        )
        sys.exit(1)

    output = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "..", "api", "data", "drive.json"
    )

    print(f"Synchronisation Google Drive → {output}")
    count = sync_drive_to_json(
        service_account_json=sa,
        token_file=token,
        folder_id=folder,
        output_path=output,
        shared_drive_id=shared,
    )
    print(f"Terminé : {count} fichiers exportés")
