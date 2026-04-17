#!/usr/bin/env python3
"""
Récupère les actualités Kiwix en interceptant la vraie requête /api/common/all
faite par le frontend et en capturant la réponse.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

KIWIX_BASE = "https://kiwix.junior-entreprises.com"
GAMMA = "https://kiwix.gamma.junior-entreprises.com"
LOGIN_URL = (
    "https://identity.junior-entreprises.com/realms/JEI/protocol/openid-connect/auth"
    "?client_id=kiwi-front&redirect_uri=https%3A%2F%2Fkiwix.junior-entreprises.com%2F"
    "&response_mode=fragment&response_type=code&scope=openid"
)
OUTPUT = Path("../api/data/kiwix-actualites.json")


def make_doc(item, source, category):
    """Convertit un item API en document RAG."""
    title = (item.get("title") or item.get("name") or item.get("nom") or "")
    if isinstance(title, dict):
        title = title.get("fr") or title.get("en") or str(title)

    # Construire le contenu textuel
    fields = []
    skip_keys = {"id", "slug", "createdAt", "updatedAt", "publishedAt", "_id"}
    for k, v in item.items():
        if k in skip_keys:
            continue
        if isinstance(v, str) and len(v) > 5:
            fields.append(f"{k}: {v}")
        elif isinstance(v, dict):
            text = v.get("fr") or v.get("en") or ""
            if text:
                fields.append(f"{k}: {text}")
        elif isinstance(v, list) and v:
            if all(isinstance(x, str) for x in v):
                fields.append(f"{k}: {', '.join(v)}")

    content = "\n".join(fields)
    url = item.get("url") or item.get("link") or f"{KIWIX_BASE}/event/{item.get('id','')}"

    return {
        "title": str(title)[:200] if title else source,
        "url": str(url),
        "category": category,
        "content": content or str(item)[:2000],
        "source": "kiwix-actualites",
        "scraped_at": datetime.now().isoformat(),
    }


captured_responses = {}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    page = ctx.new_page()

    # Intercepter TOUTES les réponses API gamma
    def on_response(resp):
        if GAMMA in resp.url and resp.status == 200 and "/api/" in resp.url:
            try:
                body = resp.body()
                data = json.loads(body)
                captured_responses[resp.url] = data
                print(f"Capturé: {resp.url} — {type(data).__name__} {'x'+str(len(data)) if isinstance(data, list) else list(data.keys())[:5] if isinstance(data, dict) else ''}")
            except Exception:
                pass

    page.on("response", on_response)

    print("Connexion SSO...")
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=20000)
    time.sleep(2)
    page.fill('input[name="username"]', os.getenv("KIWIX_USERNAME", ""))
    page.fill('input[name="password"]', os.getenv("KIWIX_PASSWORD", ""))
    page.click('input[type="submit"]')
    time.sleep(5)

    print("Chargement home...")
    page.goto(f"{KIWIX_BASE}/home", wait_until="domcontentloaded", timeout=25000)
    time.sleep(5)

    # Scroll pour déclencher plus de requêtes API
    for _ in range(10):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(1.5)

    print(f"\nRéponses capturées: {list(captured_responses.keys())}")

    # Analyser /api/common/all
    common_all = captured_responses.get(f"{GAMMA}/api/common/all")
    if common_all:
        print(f"\n/api/common/all structure:")
        if isinstance(common_all, dict):
            for k, v in common_all.items():
                if isinstance(v, list):
                    print(f"  {k}: {len(v)} items — keys: {list(v[0].keys())[:8] if v and isinstance(v[0], dict) else ''}")
                else:
                    print(f"  {k}: {str(v)[:80]}")
        elif isinstance(common_all, list):
            print(f"  {len(common_all)} items — keys: {list(common_all[0].keys())[:8] if common_all and isinstance(common_all[0], dict) else ''}")

    browser.close()

# Construire les documents
all_docs = []
for url, data in captured_responses.items():
    items = data if isinstance(data, list) else []
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list) and v:
                items = v
                break

    category = "Event" if "event" in url else "Actualite"
    for item in items:
        if isinstance(item, dict):
            doc = make_doc(item, url.split("/")[-1], category)
            if len(doc["content"]) > 30:
                all_docs.append(doc)

print(f"\nTotal docs construits: {len(all_docs)}")
if all_docs:
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_docs, f, ensure_ascii=False, indent=2)
    print(f"Sauvegardé: {OUTPUT}")
