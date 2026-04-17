#!/usr/bin/env python3
"""Explore l'API Kiwix pour trouver l'endpoint des actualités."""

import json
import os
import time
import urllib.request
import urllib.error
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

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    page = ctx.new_page()

    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=20000)
    time.sleep(2)
    page.fill('input[name="username"]', os.getenv("KIWIX_USERNAME", ""))
    page.fill('input[name="password"]', os.getenv("KIWIX_PASSWORD", ""))
    page.click('input[type="submit"]')
    time.sleep(5)
    page.goto(f"{KIWIX_BASE}/home", wait_until="domcontentloaded", timeout=25000)
    time.sleep(4)

    cookies = page.context.cookies()
    cookie_str = "; ".join(f'{c["name"]}={c["value"]}' for c in cookies)
    headers = {
        "Cookie": cookie_str,
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
        "Referer": f"{KIWIX_BASE}/home",
    }

    # Tester plusieurs endpoints candidats
    endpoints = [
        f"{GAMMA}/api/common/all",
        f"{GAMMA}/api/common/all?page=1",
        f"{GAMMA}/api/common/all?limit=100",
        f"{GAMMA}/api/event/list",
        f"{GAMMA}/api/event",
        f"{GAMMA}/api/home",
        f"{GAMMA}/api/home/feed",
        f"{GAMMA}/api/feed",
        f"{KIWIX_BASE}/api/common/all",
        f"{KIWIX_BASE}/api/home",
    ]

    for ep in endpoints:
        try:
            req = urllib.request.Request(ep, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as resp:
                body = resp.read().decode()
                try:
                    data = json.loads(body)
                    if isinstance(data, list):
                        print(f"OK LIST {ep}: {len(data)} items")
                        if data:
                            print(f"  Keys: {list(data[0].keys()) if isinstance(data[0], dict) else type(data[0])}")
                    elif isinstance(data, dict):
                        print(f"OK DICT {ep}: keys={list(data.keys())[:8]}")
                        for k, v in data.items():
                            if isinstance(v, list) and v:
                                print(f"  {k}: {len(v)} items, ex keys: {list(v[0].keys())[:6] if isinstance(v[0], dict) else ''}")
                except json.JSONDecodeError:
                    print(f"OK TEXT {ep}: {body[:100]}")
        except urllib.error.HTTPError as e:
            print(f"HTTP {e.code} {ep}")
        except Exception as e:
            print(f"ERR {ep}: {e}")

    browser.close()
