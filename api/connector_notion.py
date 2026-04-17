"""
Comply — Connecteur Notion
Récupère toutes les pages accessibles via l'intégration Notion et les exporte en JSON.

Usage API : appelé par /sync/notion
Usage CLI : python connector_notion.py
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Extraction du texte depuis les blocs Notion
# ─────────────────────────────────────────────────────────────────────────────

def _rich_text_to_str(rich_text: List[Dict]) -> str:
    """Concatène les segments rich_text en texte brut."""
    return "".join(seg.get("plain_text", "") for seg in rich_text)


def _extract_block_text(block: Dict) -> str:
    """Extrait le texte d'un bloc Notion (tous types supportés)."""
    btype = block.get("type", "")
    data = block.get(btype, {})

    text_types = {
        "paragraph", "heading_1", "heading_2", "heading_3",
        "bulleted_list_item", "numbered_list_item", "to_do",
        "toggle", "quote", "callout", "code",
    }

    if btype in text_types:
        rt = data.get("rich_text", [])
        text = _rich_text_to_str(rt)
        if btype == "heading_1":
            return f"# {text}"
        if btype == "heading_2":
            return f"## {text}"
        if btype == "heading_3":
            return f"### {text}"
        if btype == "bulleted_list_item":
            return f"- {text}"
        if btype == "numbered_list_item":
            return f"1. {text}"
        if btype == "to_do":
            checked = "x" if data.get("checked") else " "
            return f"[{checked}] {text}"
        if btype == "code":
            lang = data.get("language", "")
            return f"```{lang}\n{text}\n```"
        return text

    if btype == "divider":
        return "---"

    if btype == "table_row":
        cells = data.get("cells", [])
        return " | ".join(_rich_text_to_str(cell) for cell in cells)

    return ""


def _fetch_blocks_recursive(notion_client: Any, block_id: str, depth: int = 0) -> str:
    """Récupère récursivement le contenu textuel d'une page/bloc."""
    if depth > 5:
        return ""

    lines = []
    cursor = None

    while True:
        kwargs: Dict = {"block_id": block_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor

        try:
            response = notion_client.blocks.children.list(**kwargs)
        except Exception as exc:
            logger.warning(f"Erreur lecture blocs {block_id}: {exc}")
            break

        for block in response.get("results", []):
            text = _extract_block_text(block)
            if text:
                indent = "  " * depth
                lines.append(f"{indent}{text}")

            # Récursion sur les enfants
            if block.get("has_children"):
                child_text = _fetch_blocks_recursive(notion_client, block["id"], depth + 1)
                if child_text:
                    lines.append(child_text)

        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Récupération des pages et databases
# ─────────────────────────────────────────────────────────────────────────────

def _get_page_title(page: Dict) -> str:
    """Extrait le titre d'une page Notion."""
    props = page.get("properties", {})
    for key in ("Name", "Titre", "title", "Title"):
        if key in props:
            p = props[key]
            if p.get("type") == "title":
                return _rich_text_to_str(p.get("title", []))
    # Fallback : première propriété de type title
    for p in props.values():
        if p.get("type") == "title":
            return _rich_text_to_str(p.get("title", []))
    return "Sans titre"


def _fetch_all_pages(notion_client: Any, page_ids: List[str], database_ids: List[str]) -> List[Dict]:
    """Récupère les pages depuis les IDs fournis ou via search si vide."""
    pages = []

    if page_ids:
        for pid in page_ids:
            try:
                page = notion_client.pages.retrieve(page_id=pid)
                pages.append(page)
            except Exception as exc:
                logger.warning(f"Page {pid} inaccessible : {exc}")
    elif database_ids:
        pass  # géré plus bas
    else:
        # Search global — récupère toutes les pages accessibles
        cursor = None
        while True:
            kwargs: Dict = {"filter": {"value": "page", "property": "object"}, "page_size": 100}
            if cursor:
                kwargs["start_cursor"] = cursor
            try:
                resp = notion_client.search(**kwargs)
            except Exception as exc:
                logger.error(f"Erreur search Notion : {exc}")
                break
            pages.extend(resp.get("results", []))
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")

    return pages


def _fetch_database_entries(notion_client: Any, database_ids: List[str]) -> List[Dict]:
    """Récupère les entrées de databases Notion."""
    entries = []
    for db_id in database_ids:
        cursor = None
        while True:
            kwargs: Dict = {"database_id": db_id, "page_size": 100}
            if cursor:
                kwargs["start_cursor"] = cursor
            try:
                resp = notion_client.databases.query(**kwargs)
            except Exception as exc:
                logger.warning(f"Database {db_id} inaccessible : {exc}")
                break
            entries.extend(resp.get("results", []))
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")
    return entries


# ─────────────────────────────────────────────────────────────────────────────
# Point d'entrée principal
# ─────────────────────────────────────────────────────────────────────────────

def sync_notion_to_json(
    api_key: str,
    output_path: str,
    page_ids: Optional[List[str]] = None,
    database_ids: Optional[List[str]] = None,
) -> int:
    """
    Synchronise les pages Notion vers un fichier JSON.

    Args:
        api_key: Token d'intégration Notion (secret_...)
        output_path: Chemin du fichier JSON de sortie
        page_ids: IDs de pages spécifiques (None = toutes les pages accessibles)
        database_ids: IDs de databases à indexer

    Returns:
        Nombre de documents exportés
    """
    try:
        from notion_client import Client
    except ImportError:
        raise RuntimeError("notion-client non installé. Lancez : pip install notion-client")

    from config import NOTION_PAGE_IDS, NOTION_DATABASE_IDS
    if page_ids is None:
        page_ids = NOTION_PAGE_IDS
    if database_ids is None:
        database_ids = NOTION_DATABASE_IDS

    notion = Client(auth=api_key)
    logger.info("Connexion Notion établie")

    all_pages = _fetch_all_pages(notion, page_ids, database_ids)
    db_entries = _fetch_database_entries(notion, database_ids)
    all_items = all_pages + db_entries

    logger.info(f"Notion : {len(all_items)} pages/entrées à traiter")

    documents = []
    scraped_at = datetime.utcnow().isoformat()

    for item in all_items:
        page_id = item.get("id", "")
        title = _get_page_title(item)
        url = item.get("url", f"https://notion.so/{page_id.replace('-', '')}")

        # Extraire la catégorie depuis les propriétés si disponible
        props = item.get("properties", {})
        category = "Notion"
        for key in ("Catégorie", "Category", "Type", "Tags"):
            if key in props:
                p = props[key]
                if p.get("type") == "select" and p.get("select"):
                    category = p["select"].get("name", "Notion")
                    break
                if p.get("type") == "multi_select":
                    tags = [t.get("name", "") for t in p.get("multi_select", [])]
                    if tags:
                        category = ", ".join(tags)
                    break

        try:
            content = _fetch_blocks_recursive(notion, page_id)
        except Exception as exc:
            logger.warning(f"Impossible de lire la page {title} ({page_id}): {exc}")
            continue

        if not content.strip():
            logger.debug(f"Page vide ignorée : {title}")
            continue

        documents.append({
            "title": title,
            "url": url,
            "category": category,
            "content": content,
            "source": "notion",
            "scraped_at": scraped_at,
        })
        logger.debug(f"  OK : {title} ({len(content)} chars)")

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)

    logger.info(f"Notion sync terminé : {len(documents)} documents → {output_path}")
    return len(documents)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("NOTION_API_KEY", "")
    if not api_key:
        print("NOTION_API_KEY non définie dans .env")
        sys.exit(1)

    output = sys.argv[1] if len(sys.argv) > 1 else "./data/notion.json"
    count = sync_notion_to_json(api_key, output)
    print(f"Terminé : {count} pages exportées vers {output}")
