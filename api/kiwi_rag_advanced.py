"""
Comply RAG v2 — Assistant IA pour les Junior-Entreprises françaises
Stack légère : TF-IDF + SVD + BM25 + web search fallback
Conçu pour tourner sur n'importe quelle machine sans GPU
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import pickle
import re
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.metrics.pairwise import cosine_similarity
from tqdm import tqdm
import anthropic

from config import (
    CACHE_TTL,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CLAUDE_API_KEY,
    CLAUDE_MODEL,
    DATA_DIR,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODELS,
    GEMINI_API_KEY,
    GEMINI_BASE_URL,
    GEMINI_MODELS,
    GROQ_API_KEY,
    GROQ_BASE_URL,
    GROQ_MODELS,
    KIWI_FILE_TYPES,
    MAX_CONTEXT_DOCS,
    MAX_TOKENS,
    MIN_CONFIDENCE,
    MISTRAL_API_KEY,
    MISTRAL_MODELS,
    REDIS_URL,
    TEMPERATURE,
    VECTOR_DB_PATH,
)
from web_search import WebSearcher

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Prompt système
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es Comply, l'assistant intelligent officiel des Junior-Entreprises françaises, développé pour la CNJE (Confédération Nationale des Junior-Entreprises).

Tu maîtrises :
- La réglementation juridique et statutaire des JE (Kiwi Légal)
- Les formations disponibles (Kiwi Formation)
- Les services CNJE (Kiwi Services)
- La RSE appliquée aux JE (Kiwi RSE)
- Le réseau des Junior-Entreprises françaises et ses bonnes pratiques

**Style de réponse :**
- Réponds toujours en français
- Sois complet et pédagogue : explique les concepts, ne te contente pas de lister des points
- Structure tes réponses avec des titres et paragraphes quand la réponse est longue
- N'utilise jamais d'emojis
- Si tu n'es pas certain d'une information, dis-le clairement
- Cite tes sources documentaires quand tu t'appuies sur elles

**Comportement selon la question :**
- Si la question porte sur les JE, la CNJE ou le droit associatif : réponds en priorité avec le contexte documentaire fourni, complète avec tes connaissances si nécessaire
- Si la question est générale (informatique, droit commun, culture générale, etc.) : réponds normalement avec tes connaissances, tu es un assistant à usage général
- Si la question concerne une situation très spécifique nécessitant une validation officielle CNJE (cas particulier d'agrément, situation statutaire complexe) : réponds ce que tu sais et signale qu'une confirmation auprès du support CNJE peut être utile pour les détails précis

**Contexte documentaire disponible :**
{context}"""

FRENCH_STOPWORDS = [
    "le","la","les","de","du","des","un","une","et","en","au","aux","que","qui",
    "pour","par","sur","dans","avec","ce","se","ne","pas","plus","il","elle",
    "ils","elles","je","tu","nous","vous","on","à","est","sont","être","avoir",
    "tout","tous","très","bien","mais","ou","si","car","donc","ni","or","or",
    "leur","leurs","mon","ton","son","ma","ta","sa","nos","vos","mes","tes","ses",
    "cet","cette","ces","quel","quelle","quels","quelles","dont","où","y","même",
]

# ─────────────────────────────────────────────────────────────────────────────


class ComplyRAG:
    """
    RAG léger pour Comply :
    - TF-IDF + SVD (sklearn, ~50MB)
    - BM25 (rank_bm25)
    - Hybrid reranking
    - Web search fallback (DuckDuckGo)
    - Streaming via Claude async
    - Sessions de conversation
    """

    INDEX_PATH = "comply_index.pkl"

    def __init__(self):
        logger.info("Initialisation de Comply RAG v2...")

        # Données
        self._documents: List[Dict] = []

        # Vecteurs TF-IDF + SVD
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._svd: Optional[TruncatedSVD] = None
        self._vectors: Optional[np.ndarray] = None

        # BM25
        self._bm25: Optional[BM25Okapi] = None

        # Claude
        self._claude = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        self._async_claude = anthropic.AsyncAnthropic(api_key=CLAUDE_API_KEY)

        # Mistral
        if MISTRAL_API_KEY:
            from mistralai.client import Mistral
            self._mistral = Mistral(api_key=MISTRAL_API_KEY)
        else:
            self._mistral = None

        # DeepSeek + Gemini + Groq (OpenAI-compatible)
        from openai import AsyncOpenAI
        self._deepseek = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL) if DEEPSEEK_API_KEY else None
        self._gemini = AsyncOpenAI(api_key=GEMINI_API_KEY, base_url=GEMINI_BASE_URL) if GEMINI_API_KEY else None
        self._groq = AsyncOpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL) if GROQ_API_KEY else None

        # Redis cache
        self._redis = None
        try:
            import redis
            r = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
            r.ping()
            self._redis = r
            logger.info("Cache Redis connecte")
        except Exception as e:
            logger.warning(f"Redis indisponible, cache desactive : {e}")

        # Web search
        from config import ENABLE_WEB_SEARCH
        self._web = WebSearcher() if ENABLE_WEB_SEARCH else None

        # Sessions
        self._sessions: Dict[str, List[Dict]] = defaultdict(list)

        # Charge l'index ou indexe
        index_path = Path(self.INDEX_PATH)
        if index_path.exists():
            self._load_index(index_path)
        else:
            self._load_data()

        logger.info(f"RAG prêt — {len(self._documents)} chunks indexés")

    # ─────────────────────────────────────────────────────────────────────────
    # Persistance index
    # ─────────────────────────────────────────────────────────────────────────

    def _save_index(self):
        path = Path(self.INDEX_PATH)
        with open(path, "wb") as f:
            pickle.dump({
                "documents": self._documents,
                "vectorizer": self._vectorizer,
                "svd": self._svd,
                "vectors": self._vectors,
            }, f)
        logger.info(f"Index sauvegardé ({path.stat().st_size // 1024} KB)")

    def _load_index(self, path: Path):
        logger.info(f"Chargement de l'index existant : {path}")
        try:
            with open(path, "rb") as f:
                data = pickle.load(f)
            self._documents = data["documents"]
            self._vectorizer = data["vectorizer"]
            self._svd = data["svd"]
            self._vectors = data["vectors"]
            self._build_bm25()
            logger.info(f"Index chargé — {len(self._documents)} chunks")
        except Exception as exc:
            logger.warning(f"Index corrompu, réindexation : {exc}")
            self._load_data()

    # ─────────────────────────────────────────────────────────────────────────
    # Chargement et traitement des données
    # ─────────────────────────────────────────────────────────────────────────

    def _load_data(self):
        data_path = Path(DATA_DIR)
        if not data_path.exists():
            logger.warning(f"DATA_DIR introuvable : {DATA_DIR}")
            return

        json_files = list(data_path.glob("*.json"))
        if not json_files:
            logger.warning(f"Aucun fichier JSON dans {DATA_DIR}")
            return

        logger.info(f"Indexation de {len(json_files)} fichiers...")
        all_docs: List[Dict] = []

        for fp in tqdm(json_files, desc="Chargement"):
            try:
                docs = self._process_file(fp)
                all_docs.extend(docs)
                logger.info(f"  {fp.name}: {len(docs)} chunks")
            except Exception as exc:
                logger.error(f"Erreur {fp.name}: {exc}")

        if all_docs:
            self._documents = all_docs
            self._build_tfidf()
            self._build_bm25()
            self._save_index()
            logger.info(f"Indexation terminée — {len(all_docs)} chunks")

    def _detect_type(self, filepath: Path) -> str:
        name = filepath.stem.lower()
        for pattern, ftype in KIWI_FILE_TYPES.items():
            if pattern in name:
                return ftype
        return "general"

    def _process_file(self, filepath: Path) -> List[Dict]:
        ftype = self._detect_type(filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        dispatch = {
            "faq": self._process_faq,
            "legal": self._process_legal,
            "je": self._process_je,
        }
        handler = dispatch.get(ftype, self._process_generic)
        return handler(data, filepath.name, ftype)

    def _process_faq(self, data: Any, source: str, ftype: str = "faq") -> List[Dict]:
        docs = []
        items = data if isinstance(data, list) else data.get("items", [data])
        for item in items:
            if not isinstance(item, dict):
                continue
            question = item.get("question", item.get("titre", ""))
            answer = item.get("answer", item.get("reponse", item.get("content", "")))
            category = str(item.get("category", item.get("categorie", "FAQ")))
            if question and answer:
                content = f"Question : {question}\n\nRéponse : {answer}"
                for chunk in self._chunk(content):
                    docs.append(self._make_doc(chunk, source, "faq", category, str(question)[:200]))
        return docs

    def _process_legal(self, data: Any, source: str, ftype: str = "legal") -> List[Dict]:
        docs = []
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            title = item.get("title", item.get("titre", ""))
            category = str(item.get("category", item.get("categorie", "Légal")))
            url = str(item.get("url", ""))
            content = item.get("content", item.get("contenu", item.get("text", "")))
            if not content and isinstance(item.get("sections"), list):
                content = "\n\n".join(
                    f"{s.get('titre','')}\n{s.get('content','')}"
                    for s in item["sections"] if isinstance(s, dict)
                )
            if content:
                for chunk in self._chunk(str(content)):
                    docs.append(self._make_doc(chunk, source, "legal", category, str(title)[:200], url))
        return docs

    def _process_je(self, data: Any, source: str, ftype: str = "je") -> List[Dict]:
        docs = []
        items = data if isinstance(data, list) else data.get("junior_entreprises", [data])
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("nom") or item.get("name") or item.get("denomination") or ""
            school = item.get("ecole") or item.get("school") or ""
            city = item.get("ville") or item.get("city") or ""
            domain = item.get("domaine") or item.get("domain") or ""
            contact = item.get("email") or item.get("contact") or ""
            desc = item.get("description") or item.get("activite") or ""
            parts = [f"Junior-Entreprise : {name}"]
            if school: parts.append(f"École : {school}")
            if city: parts.append(f"Ville : {city}")
            if domain: parts.append(f"Domaine : {domain}")
            if contact: parts.append(f"Contact : {contact}")
            if desc: parts.append(f"Description : {desc}")
            content = "\n".join(parts)
            if name:
                docs.append(self._make_doc(content, source, "je", str(domain or "JE"), str(name)[:200]))
        return docs

    def _process_generic(self, data: Any, source: str, ftype: str = "general") -> List[Dict]:
        docs = []
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, str):
                content, title = item, ""
            elif isinstance(item, dict):
                title = item.get("title", item.get("titre", item.get("nom", "")))
                content = item.get("content", item.get("contenu", item.get("text", "")))
                if not content:
                    content = " ".join(str(v) for v in item.values() if isinstance(v, str) and len(v) > 20)
            else:
                continue
            if content:
                for chunk in self._chunk(str(content)):
                    docs.append(self._make_doc(chunk, source, ftype, ftype, str(title)[:200] if title else ""))
        return docs

    @staticmethod
    def _make_doc(content: str, source: str, doc_type: str, category: str, title: str = "", url: str = "") -> Dict:
        return {
            "content": content,
            "source": source,
            "type": doc_type,
            "category": category,
            "title": title,
            "url": url,
        }

    @staticmethod
    def _chunk(text: str) -> List[str]:
        text = re.sub(r"\s+", " ", text.strip())
        if len(text) <= CHUNK_SIZE:
            return [text] if len(text) > 30 else []
        chunks = []
        start = 0
        while start < len(text):
            end = start + CHUNK_SIZE
            if end < len(text):
                for sep in ["\n\n", "\n", ". ", " "]:
                    pos = text.rfind(sep, start, end)
                    if pos > start:
                        end = pos + len(sep)
                        break
            chunk = text[start:end].strip()
            if len(chunk) > 30:
                chunks.append(chunk)
            start = end - CHUNK_OVERLAP
        return chunks

    # ─────────────────────────────────────────────────────────────────────────
    # Indexation
    # ─────────────────────────────────────────────────────────────────────────

    def _build_tfidf(self):
        logger.info("Construction du TF-IDF + SVD...")
        contents = [d["content"] for d in self._documents]

        self._vectorizer = TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 2),
            min_df=1,
            max_df=0.9,
            stop_words=FRENCH_STOPWORDS,
            sublinear_tf=True,
        )
        tfidf_matrix = self._vectorizer.fit_transform(contents)

        n_components = min(300, tfidf_matrix.shape[1] - 1, len(contents) - 1)
        self._svd = TruncatedSVD(n_components=n_components, random_state=42)
        self._vectors = self._svd.fit_transform(tfidf_matrix)

        # Normalisation pour cosine similarity
        norms = np.linalg.norm(self._vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1
        self._vectors = self._vectors / norms

        logger.info(f"TF-IDF: {tfidf_matrix.shape}, SVD: {self._vectors.shape}")

    def _build_bm25(self):
        if not self._documents:
            return
        tokenized = [self._tokenize(d["content"]) for d in self._documents]
        self._bm25 = BM25Okapi(tokenized)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return re.sub(r"[^\w\s]", " ", text.lower()).split()

    # ─────────────────────────────────────────────────────────────────────────
    # Recherche hybride
    # ─────────────────────────────────────────────────────────────────────────

    def search(self, query: str, n: int = MAX_CONTEXT_DOCS) -> Tuple[List[Dict], float]:
        if not self._documents or self._vectors is None:
            return [], 0.0

        semantic = self._semantic_search(query, n * 2)
        bm25 = self._bm25_search(query, n * 2)
        combined = self._hybrid_rerank(semantic, bm25, n)
        max_score = combined[0]["score"] if combined else 0.0
        return combined, max_score

    def _semantic_search(self, query: str, n: int) -> List[Tuple[int, float]]:
        if self._vectorizer is None or self._svd is None:
            return []
        q_tfidf = self._vectorizer.transform([query])
        q_vec = self._svd.transform(q_tfidf)
        norm = np.linalg.norm(q_vec)
        if norm > 0:
            q_vec = q_vec / norm
        scores = cosine_similarity(q_vec, self._vectors)[0]
        top_idx = np.argsort(scores)[::-1][:n]
        return [(int(i), float(scores[i])) for i in top_idx if scores[i] > 0.05]

    def _bm25_search(self, query: str, n: int) -> List[Tuple[int, float]]:
        if not self._bm25:
            return []
        tokens = self._tokenize(query)
        scores = self._bm25.get_scores(tokens)
        top_idx = np.argsort(scores)[::-1][:n]
        max_s = float(scores[top_idx[0]]) if len(top_idx) > 0 else 1.0
        if max_s == 0:
            return []
        return [(int(i), float(scores[i]) / max_s) for i in top_idx if scores[i] > 0]

    def _hybrid_rerank(
        self,
        semantic: List[Tuple[int, float]],
        bm25: List[Tuple[int, float]],
        n: int,
        alpha: float = 0.65,
    ) -> List[Dict]:
        scores: Dict[int, Dict] = {}
        for idx, score in semantic:
            scores[idx] = {"sem": score, "bm25": 0.0}
        for idx, score in bm25:
            if idx in scores:
                scores[idx]["bm25"] = score
            else:
                scores[idx] = {"sem": 0.0, "bm25": score}

        results = []
        for idx, s in scores.items():
            combined = alpha * s["sem"] + (1 - alpha) * s["bm25"]
            doc = self._documents[idx].copy()
            doc["score"] = combined
            results.append(doc)

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:n]

    # ─────────────────────────────────────────────────────────────────────────
    # Génération de réponse
    # ─────────────────────────────────────────────────────────────────────────

    def _format_context(self, results: List[Dict]) -> str:
        if not results:
            return "Aucun document trouvé dans la base de connaissances."
        parts = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            doc_type = r.get("type", "")
            source = r.get("source", "")
            header = f"[Document {i}"
            if title:
                header += f" — {title}"
            if doc_type:
                header += f" ({doc_type})"
            if source:
                header += f" | {source}"
            header += "]"
            parts.append(f"{header}\n{r['content']}")
        return "\n\n" + "\n\n".join(parts)

    def _build_messages(self, question: str, session_id: Optional[str]) -> List[Dict]:
        history = list(self._sessions.get(session_id, [])[-10:]) if session_id else []
        return history + [{"role": "user", "content": question}]

    def _get_context(self, question: str) -> Tuple[str, str, float, int]:
        """Retourne (context, source, confidence, docs_found)"""
        results, confidence = self.search(question)

        if confidence >= MIN_CONFIDENCE:
            return self._format_context(results), "rag", confidence, len(results)

        if self._web:
            logger.info(f"Confiance trop faible ({confidence:.2f}), recherche web...")
            web_results = self._web.search(question)
            if web_results:
                if self._web.has_reliable_results(web_results):
                    return self._web.format_context(web_results), "web", 0.5, len(web_results)
                # Résultats web non officiels : on les inclut quand même comme contexte partiel
                return self._web.format_context(web_results), "web", 0.3, len(web_results)

        # Pas de contexte pertinent : Claude répond avec ses connaissances générales
        if results:
            return self._format_context(results), "rag", confidence, len(results)
        return "", "general", 0.0, 0

    # ── Cache Redis ───────────────────────────────────────────────────────────

    def _cache_key(self, question: str, model: str) -> str:
        """Génère une clé de cache unique basée sur la question et le modèle."""
        raw = f"{question.lower().strip()}:{model}"
        return "comply:" + hashlib.sha256(raw.encode()).hexdigest()

    def _cache_get(self, question: str, model: str) -> Optional[str]:
        if not self._redis:
            return None
        try:
            return self._redis.get(self._cache_key(question, model))
        except Exception:
            return None

    def _cache_set(self, question: str, model: str, response: str):
        if not self._redis:
            return
        try:
            self._redis.setex(self._cache_key(question, model), CACHE_TTL, response)
        except Exception:
            pass

    def cache_flush(self):
        """Vide tout le cache (appelé lors d'une réindexation)."""
        if not self._redis:
            return
        try:
            keys = self._redis.keys("comply:*")
            if keys:
                self._redis.delete(*keys)
            logger.info(f"Cache Redis vide ({len(keys)} entrees supprimees)")
        except Exception as e:
            logger.warning(f"Erreur flush cache : {e}")

    def _mistral_messages(self, system: str, messages: List[Dict]) -> List[Dict]:
        """Convertit le format Anthropic (system séparé) vers le format Mistral (system en premier message)."""
        return [{"role": "system", "content": system}] + messages

    def answer(self, question: str, session_id: Optional[str] = None, model: Optional[str] = None) -> Dict[str, Any]:
        use_model = model or CLAUDE_MODEL

        # Cache hit — pas d'appel LLM si déjà en cache (hors sessions avec historique)
        if not session_id:
            cached = self._cache_get(question, use_model)
            if cached:
                logger.info(f"Cache hit : {question[:60]}")
                return {
                    "answer": cached,
                    "source": "cache",
                    "confidence": 1.0,
                    "documents_found": 0,
                    "session_id": None,
                    "model": use_model,
                }

        context, source, confidence, docs_found = self._get_context(question)

        messages = self._build_messages(question, session_id)
        system = SYSTEM_PROMPT.format(context=context if context else "Aucun document trouvé dans la base de connaissances pour cette question.")

        if use_model in MISTRAL_MODELS:
            if not self._mistral:
                raise ValueError("Clé API Mistral non configurée")
            response = self._mistral.chat.complete(
                model=use_model,
                messages=self._mistral_messages(system, messages),
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
            )
            answer_text = response.choices[0].message.content
        elif use_model in DEEPSEEK_MODELS:
            if not self._deepseek:
                raise ValueError("Clé API DeepSeek non configurée")
            import asyncio
            response = asyncio.get_event_loop().run_until_complete(
                self._deepseek.chat.completions.create(
                    model=use_model,
                    messages=self._mistral_messages(system, messages),
                    max_tokens=MAX_TOKENS,
                    temperature=TEMPERATURE,
                )
            )
            answer_text = response.choices[0].message.content
        elif use_model in GEMINI_MODELS:
            if not self._gemini:
                raise ValueError("Clé API Gemini non configurée")
            import asyncio
            response = asyncio.get_event_loop().run_until_complete(
                self._gemini.chat.completions.create(
                    model=use_model,
                    messages=self._mistral_messages(system, messages),
                    max_tokens=MAX_TOKENS,
                    temperature=TEMPERATURE,
                )
            )
            answer_text = response.choices[0].message.content
        elif use_model in GROQ_MODELS:
            if not self._groq:
                raise ValueError("Clé API Groq non configurée")
            import asyncio
            response = asyncio.get_event_loop().run_until_complete(
                self._groq.chat.completions.create(
                    model=use_model,
                    messages=self._mistral_messages(system, messages),
                    max_tokens=MAX_TOKENS,
                    temperature=TEMPERATURE,
                )
            )
            answer_text = response.choices[0].message.content
        else:
            response = self._claude.messages.create(
                model=use_model,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                system=system,
                messages=messages,
            )
            answer_text = response.content[0].text

        if session_id:
            self._sessions[session_id].extend([
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer_text},
            ])
        else:
            self._cache_set(question, use_model, answer_text)

        return {
            "answer": answer_text,
            "source": source,
            "confidence": float(confidence),
            "documents_found": docs_found,
            "session_id": session_id,
            "model": use_model,
        }

    async def stream_answer(self, question: str, session_id: Optional[str] = None, model: Optional[str] = None) -> AsyncGenerator[str, None]:
        use_model = model or CLAUDE_MODEL
        full_response = ""

        # Cache hit — stream la réponse cached token par token
        if not session_id:
            cached = self._cache_get(question, use_model)
            if cached:
                logger.info(f"Cache hit (stream) : {question[:60]}")
                chunk_size = 8
                for i in range(0, len(cached), chunk_size):
                    yield cached[i:i + chunk_size]
                    await asyncio.sleep(0.01)
                return

        context, source, confidence, docs_found = self._get_context(question)

        messages = self._build_messages(question, session_id)
        system = SYSTEM_PROMPT.format(context=context if context else "Aucun document trouvé dans la base de connaissances pour cette question.")

        if use_model in MISTRAL_MODELS:
            if not self._mistral:
                yield "Erreur : clé API Mistral non configurée."
                return
            async with self._mistral.chat.stream_async(
                model=use_model,
                messages=self._mistral_messages(system, messages),
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
            ) as stream:
                async for chunk in stream:
                    content = chunk.data.choices[0].delta.content
                    if content:
                        full_response += content
                        yield content

        elif use_model in DEEPSEEK_MODELS:
            if not self._deepseek:
                yield "Erreur : clé API DeepSeek non configurée."
                return
            stream = await self._deepseek.chat.completions.create(
                model=use_model,
                messages=self._mistral_messages(system, messages),
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                stream=True,
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    full_response += content
                    yield content

        elif use_model in GEMINI_MODELS:
            if not self._gemini:
                yield "Erreur : clé API Gemini non configurée."
                return
            stream = await self._gemini.chat.completions.create(
                model=use_model,
                messages=self._mistral_messages(system, messages),
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                stream=True,
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    full_response += content
                    yield content

        elif use_model in GROQ_MODELS:
            if not self._groq:
                yield "Erreur : clé API Groq non configurée."
                return
            stream = await self._groq.chat.completions.create(
                model=use_model,
                messages=self._mistral_messages(system, messages),
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                stream=True,
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    full_response += content
                    yield content

        else:
            async with self._async_claude.messages.stream(
                model=use_model,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                system=system,
                messages=messages,
            ) as stream:
                async for chunk in stream.text_stream:
                    full_response += chunk
                    yield chunk

        if session_id:
            self._sessions[session_id].extend([
                {"role": "user", "content": question},
                {"role": "assistant", "content": full_response},
            ])
        else:
            self._cache_set(question, use_model, full_response)

    # ─────────────────────────────────────────────────────────────────────────
    # Utilitaires
    # ─────────────────────────────────────────────────────────────────────────

    def reindex(self) -> Dict[str, Any]:
        Path(self.INDEX_PATH).unlink(missing_ok=True)
        self._documents = []
        self._vectorizer = self._svd = self._vectors = self._bm25 = None
        self._load_data()
        return {"status": "ok", "documents_indexed": len(self._documents)}

    def new_session(self) -> str:
        sid = str(uuid.uuid4())
        self._sessions[sid] = []
        return sid

    def get_session_history(self, session_id: str) -> List[Dict]:
        return list(self._sessions.get(session_id, []))

    def clear_session(self, session_id: str):
        self._sessions.pop(session_id, None)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_documents": len(self._documents),
            "active_sessions": len(self._sessions),
            "claude_model": CLAUDE_MODEL,
            "bm25_ready": self._bm25 is not None,
            "tfidf_ready": self._vectorizer is not None,
            "web_search_enabled": self._web is not None and self._web.available,
            "data_dir": DATA_DIR,
        }
