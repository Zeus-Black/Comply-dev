"""
Module de recherche web pour Comply RAG
Fallback quand la base locale ne contient pas la réponse
"""

import logging
from dataclasses import dataclass, field
from typing import List

from config import TRUSTED_DOMAINS, WEB_SEARCH_MAX_RESULTS, CNJE_TICKET_URL

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    body: str
    is_reliable: bool
    score: float = 0.0


TICKET_MESSAGE = f"""Je n'ai pas trouvé d'information suffisamment fiable pour répondre à cette question avec certitude.

Pour obtenir une réponse précise et validée, vous pouvez soumettre un ticket au support CNJE : [Contacter le support CNJE]({CNJE_TICKET_URL})

N'hésitez pas à décrire votre situation en détail pour obtenir l'aide la plus adaptée."""


class WebSearcher:
    def __init__(self):
        try:
            from duckduckgo_search import DDGS
            self._ddgs = DDGS
            self.available = True
            logger.info("Web search (DuckDuckGo) activé")
        except ImportError:
            logger.warning("duckduckgo-search non installé — recherche web désactivée")
            self.available = False

    def search(self, query: str, max_results: int = WEB_SEARCH_MAX_RESULTS) -> List[SearchResult]:
        if not self.available:
            return []

        try:
            with self._ddgs() as ddgs:
                raw = list(ddgs.text(
                    f"{query} junior entreprise France",
                    max_results=max_results,
                    region="fr-fr",
                ))
        except Exception as exc:
            logger.error(f"Recherche web échouée : {exc}")
            return []

        results = []
        for item in raw:
            url = item.get("href", "")
            is_reliable = any(domain in url for domain in TRUSTED_DOMAINS)
            results.append(SearchResult(
                title=item.get("title", ""),
                url=url,
                body=item.get("body", ""),
                is_reliable=is_reliable,
            ))

        # Trier : sources fiables en premier
        results.sort(key=lambda r: r.is_reliable, reverse=True)
        logger.info(f"Recherche web : {len(results)} résultats, "
                    f"{sum(r.is_reliable for r in results)} fiables")
        return results

    def has_reliable_results(self, results: List[SearchResult]) -> bool:
        return any(r.is_reliable for r in results)

    def format_context(self, results: List[SearchResult]) -> str:
        parts = []
        for r in results:
            reliability = "Source officielle" if r.is_reliable else "Source non vérifiée"
            parts.append(
                f"**{r.title}** ({reliability})\n{r.body}\nSource : {r.url}"
            )
        return "\n\n---\n\n".join(parts)

    def get_ticket_message(self) -> str:
        return TICKET_MESSAGE
