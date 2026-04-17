"""
Comply — Connecteur Google Drive
Récupère tous les documents accessibles (Google Docs, PDF, TXT) et les exporte en JSON.

Authentification supportée :
  1. Compte de service (GOOGLE_DRIVE_SERVICE_ACCOUNT='{...json...}')
  2. Token OAuth (GOOGLE_DRIVE_TOKEN_FILE=./drive_token.json)

Usage API : appelé par /sync/drive
Usage CLI : python connector_drive.py
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

MIME_GOOGLE_DOC = "application/vnd.google-apps.document"
MIME_GOOGLE_SHEET = "application/vnd.google-apps.spreadsheet"
MIME_GOOGLE_SLIDE = "application/vnd.google-apps.presentation"
MIME_PDF = "application/pdf"
MIME_TEXT = "text/plain"
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

EXPORTABLE = {
    MIME_GOOGLE_DOC: "text/plain",
    MIME_GOOGLE_SHEET: "text/csv",
    MIME_GOOGLE_SLIDE: "text/plain",
}


# ─────────────────────────────────────────────────────────────────────────────
# Authentification
# ─────────────────────────────────────────────────────────────────────────────

def _build_service(service_account_json: str = "", token_file: str = ""):
    """Construit le service Google Drive API."""
    try:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account
        from google.oauth2.credentials import Credentials
    except ImportError:
        raise RuntimeError(
            "google-api-python-client non installé. "
            "Lancez : pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
        )

    if service_account_json:
        info = json.loads(service_account_json)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    elif token_file and os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        if creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            with open(token_file, "w") as f:
                f.write(creds.to_json())
    else:
        raise ValueError(
            "Credentials Google Drive manquantes. "
            "Configurez GOOGLE_DRIVE_SERVICE_ACCOUNT ou GOOGLE_DRIVE_TOKEN_FILE dans .env"
        )

    return build("drive", "v3", credentials=creds, cache_discovery=False)


# ─────────────────────────────────────────────────────────────────────────────
# Listing et extraction
# ─────────────────────────────────────────────────────────────────────────────

def _list_files(service, folder_id: str = "", shared_drive_id: str = "") -> List[Dict]:
    """Liste tous les fichiers accessibles (récursivement si folder_id fourni)."""
    files = []
    page_token = None

    query_parts = [
        "trashed = false",
        f"mimeType != 'application/vnd.google-apps.folder'",
    ]
    if folder_id:
        query_parts.insert(0, f"'{folder_id}' in parents")

    query = " and ".join(query_parts)

    kwargs: Dict = {
        "q": query,
        "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, webViewLink, parents)",
        "pageSize": 100,
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": True,
    }
    if shared_drive_id:
        kwargs["driveId"] = shared_drive_id
        kwargs["corpora"] = "drive"

    while True:
        if page_token:
            kwargs["pageToken"] = page_token
        try:
            resp = service.files().list(**kwargs).execute()
        except Exception as exc:
            logger.error(f"Erreur listing Drive : {exc}")
            break
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return files


def _extract_text_from_file(service, file: Dict) -> Optional[str]:
    """Extrait le texte d'un fichier Drive selon son type MIME."""
    fid = file["id"]
    mime = file["mimeType"]

    try:
        # Google Docs natifs → export texte
        if mime in EXPORTABLE:
            export_mime = EXPORTABLE[mime]
            content = service.files().export(fileId=fid, mimeType=export_mime).execute()
            if isinstance(content, bytes):
                return content.decode("utf-8", errors="replace")
            return str(content)

        # PDF → extraction via pypdf
        if mime == MIME_PDF:
            from googleapiclient.http import MediaIoBaseDownload
            buf = BytesIO()
            request = service.files().get_media(fileId=fid, supportsAllDrives=True)
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            buf.seek(0)
            try:
                from pypdf import PdfReader
                reader = PdfReader(buf)
                pages_text = [p.extract_text() or "" for p in reader.pages]
                return "\n\n".join(t.strip() for t in pages_text if t.strip())
            except Exception as exc:
                logger.warning(f"Extraction PDF {file['name']} échouée : {exc}")
                return None

        # DOCX → extraction via python-docx
        if mime == MIME_DOCX:
            from googleapiclient.http import MediaIoBaseDownload
            from docx import Document
            buf = BytesIO()
            request = service.files().get_media(fileId=fid, supportsAllDrives=True)
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            buf.seek(0)
            doc = Document(buf)
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())

        # Texte brut
        if mime == MIME_TEXT or mime.startswith("text/"):
            from googleapiclient.http import MediaIoBaseDownload
            buf = BytesIO()
            request = service.files().get_media(fileId=fid, supportsAllDrives=True)
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return buf.getvalue().decode("utf-8", errors="replace")

    except Exception as exc:
        logger.warning(f"Extraction {file['name']} ({mime}) : {exc}")

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Point d'entrée principal
# ─────────────────────────────────────────────────────────────────────────────

def sync_drive_to_json(
    service_account_json: str = "",
    token_file: str = "",
    folder_id: str = "",
    output_path: str = "./data/drive.json",
    shared_drive_id: str = "",
) -> int:
    """
    Synchronise Google Drive vers un fichier JSON.

    Args:
        service_account_json: Contenu JSON du compte de service (string)
        token_file: Chemin vers le fichier token OAuth
        folder_id: ID du dossier Drive à indexer (vide = tout le Drive accessible)
        output_path: Chemin du fichier JSON de sortie
        shared_drive_id: ID du Shared Drive (optionnel)

    Returns:
        Nombre de documents exportés
    """
    service = _build_service(service_account_json, token_file)
    logger.info("Service Google Drive connecté")

    files = _list_files(service, folder_id, shared_drive_id)
    logger.info(f"Drive : {len(files)} fichiers trouvés")

    documents = []
    scraped_at = datetime.utcnow().isoformat()

    for f in files:
        name = f.get("name", "Sans titre")
        mime = f.get("mimeType", "")
        url = f.get("webViewLink", "")

        text = _extract_text_from_file(service, f)
        if not text or not text.strip():
            logger.debug(f"Ignoré (vide ou non supporté) : {name}")
            continue

        # Déduire la catégorie depuis le type de fichier
        if mime == MIME_GOOGLE_DOC:
            category = "Document"
        elif mime == MIME_GOOGLE_SHEET:
            category = "Tableur"
        elif mime == MIME_GOOGLE_SLIDE:
            category = "Présentation"
        elif mime == MIME_PDF:
            category = "PDF"
        else:
            category = "Drive"

        documents.append({
            "title": name,
            "url": url,
            "category": category,
            "content": text[:50000],
            "source": "drive",
            "scraped_at": scraped_at,
        })
        logger.debug(f"  OK : {name} ({len(text)} chars)")

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f_out:
        json.dump(documents, f_out, ensure_ascii=False, indent=2)

    logger.info(f"Drive sync terminé : {len(documents)} documents → {output_path}")
    return len(documents)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from dotenv import load_dotenv
    load_dotenv()

    sa = os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT", "")
    token = os.getenv("GOOGLE_DRIVE_TOKEN_FILE", "")
    folder = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")

    if not sa and not token:
        print("Configurez GOOGLE_DRIVE_SERVICE_ACCOUNT ou GOOGLE_DRIVE_TOKEN_FILE dans .env")
        sys.exit(1)

    output = sys.argv[1] if len(sys.argv) > 1 else "./data/drive.json"
    count = sync_drive_to_json(
        service_account_json=sa,
        token_file=token,
        folder_id=folder,
        output_path=output,
    )
    print(f"Terminé : {count} fichiers exportés vers {output}")
