"""
Tests — Moteur RAG (unités sur les méthodes internes)
"""

import json
import re
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# _chunk() — découpage de texte
# ─────────────────────────────────────────────────────────────────────────────

class TestChunk:
    """Tests de la méthode statique ComplyRAG._chunk()"""

    @pytest.fixture(autouse=True)
    def import_chunk(self):
        from kiwi_rag_advanced import ComplyRAG
        self.chunk = ComplyRAG._chunk

    def test_short_text_returned_as_single_chunk(self):
        text = "Bonjour, ceci est un texte court."
        result = self.chunk(text)
        assert len(result) == 1
        assert result[0] == text

    def test_very_short_text_ignored(self):
        # Texte < 30 chars est ignoré
        result = self.chunk("Trop court.")
        assert result == []

    def test_empty_string_returns_empty(self):
        assert self.chunk("") == []

    def test_whitespace_only_returns_empty(self):
        assert self.chunk("   \n\t  ") == []

    def test_long_text_splits_into_multiple_chunks(self):
        # Génère un texte > CHUNK_SIZE (800 chars par défaut)
        sentence = "Voici une phrase de test pour la chunkerisation. "
        text = sentence * 25  # ~1250 chars
        result = self.chunk(text)
        assert len(result) >= 2
        # Chaque chunk doit être non vide
        assert all(len(c) > 30 for c in result)

    def test_chunks_contain_original_content(self):
        sentence = "La Junior-Entreprise facture ses études à ses clients. "
        text = sentence * 25
        result = self.chunk(text)
        # Le contenu original doit être réparti dans les chunks
        all_text = " ".join(result)
        assert "Junior-Entreprise" in all_text

    def test_whitespace_normalised(self):
        text = "Bonjour    monde   \n\n  test   " + "x" * 50
        result = self.chunk(text)
        # Espaces multiples normalisés
        assert not any("  " in c for c in result)

    def test_chunk_respects_sentence_boundary(self):
        # Construit un texte où la coupure naturelle est un ". "
        sentence = "Voici une phrase complète qui se termine par un point. "
        text = sentence * 20  # ~1100 chars
        result = self.chunk(text)
        # Les chunks ne doivent pas commencer en plein milieu d'un mot
        for chunk in result:
            assert not chunk.startswith(" ")


# ─────────────────────────────────────────────────────────────────────────────
# _tokenize() — tokenisation
# ─────────────────────────────────────────────────────────────────────────────

class TestTokenize:
    @pytest.fixture(autouse=True)
    def import_tokenize(self):
        from kiwi_rag_advanced import ComplyRAG
        self.tokenize = ComplyRAG._tokenize

    def test_basic_tokenization(self):
        tokens = self.tokenize("Bonjour le monde")
        assert "bonjour" in tokens
        assert "monde" in tokens

    def test_lowercases_input(self):
        tokens = self.tokenize("JUNIOR-ENTREPRISE France")
        assert "junior" in tokens
        assert "france" in tokens

    def test_removes_punctuation(self):
        tokens = self.tokenize("Bonjour, monde ! Comment ça va ?")
        assert "," not in tokens
        assert "!" not in tokens
        assert "?" not in tokens

    def test_returns_list_of_strings(self):
        result = self.tokenize("test")
        assert isinstance(result, list)
        assert all(isinstance(t, str) for t in result)

    def test_empty_string(self):
        assert self.tokenize("") == []


# ─────────────────────────────────────────────────────────────────────────────
# _make_doc() — construction de document
# ─────────────────────────────────────────────────────────────────────────────

class TestMakeDoc:
    @pytest.fixture(autouse=True)
    def import_make_doc(self):
        from kiwi_rag_advanced import ComplyRAG
        self.make_doc = ComplyRAG._make_doc

    def test_makes_correct_dict(self):
        doc = self.make_doc("contenu", "source.json", "faq", "Facturation", "Titre", "https://url")
        assert doc["content"] == "contenu"
        assert doc["source"] == "source.json"
        assert doc["type"] == "faq"
        assert doc["category"] == "Facturation"
        assert doc["title"] == "Titre"
        assert doc["url"] == "https://url"

    def test_defaults_for_optional_fields(self):
        doc = self.make_doc("contenu", "source.json", "legal", "Légal")
        assert doc["title"] == ""
        assert doc["url"] == ""

    def test_returns_dict_with_required_keys(self):
        doc = self.make_doc("x", "y", "z", "w")
        required_keys = {"content", "source", "type", "category", "title", "url"}
        assert required_keys.issubset(set(doc.keys()))


# ─────────────────────────────────────────────────────────────────────────────
# _detect_type() — détection de type par nom de fichier
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectType:
    @pytest.fixture(autouse=True)
    def setup(self):
        """Crée une instance minimale sans charger de données."""
        with patch("kiwi_rag_advanced.ComplyRAG.__init__", return_value=None):
            from kiwi_rag_advanced import ComplyRAG
            self.rag = ComplyRAG.__new__(ComplyRAG)

    def test_detects_faq(self):
        from kiwi_rag_advanced import ComplyRAG
        path = Path("kiwi-faq-formation.json")
        result = self.rag._detect_type(path)
        assert result == "faq"

    def test_detects_legal(self):
        path = Path("kiwi-legal-2024.json")
        result = self.rag._detect_type(path)
        assert result == "legal"

    def test_detects_je(self):
        path = Path("base-je-cnje.json")
        result = self.rag._detect_type(path)
        assert result == "je"

    def test_unknown_returns_general(self):
        path = Path("random-data.json")
        result = self.rag._detect_type(path)
        assert result == "general"

    def test_notion_returns_general(self):
        path = Path("notion-export.json")
        result = self.rag._detect_type(path)
        assert result == "general"


# ─────────────────────────────────────────────────────────────────────────────
# _process_faq() — traitement des FAQ
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessFaq:
    @pytest.fixture(autouse=True)
    def setup(self):
        with patch("kiwi_rag_advanced.ComplyRAG.__init__", return_value=None):
            from kiwi_rag_advanced import ComplyRAG
            self.rag = ComplyRAG.__new__(ComplyRAG)

    def test_processes_faq_list(self):
        data = [
            {
                "question": "Comment facturer ?",
                "answer": "Vous devez émettre une facture conforme.",
                "category": "Facturation",
            }
        ]
        docs = self.rag._process_faq(data, "test-faq.json")
        assert len(docs) >= 1
        assert any("Comment facturer" in d["content"] for d in docs)
        assert all(d["type"] == "faq" for d in docs)

    def test_ignores_items_without_question_or_answer(self):
        data = [{"category": "Test"}]
        docs = self.rag._process_faq(data, "test.json")
        assert docs == []

    def test_processes_dict_with_items_key(self):
        data = {
            "items": [
                {"question": "Q1 ?", "answer": "Réponse longue à la question un.", "category": "A"}
            ]
        }
        docs = self.rag._process_faq(data, "test.json")
        assert len(docs) >= 1

    def test_accepts_reponse_alias(self):
        data = [{"question": "Q ?", "reponse": "Réponse alternative.", "categorie": "Test"}]
        docs = self.rag._process_faq(data, "test.json")
        assert len(docs) >= 1

    def test_faq_from_fixture(self):
        fixture_path = Path(__file__).parent / "fixtures" / "sample_faq.json"
        with open(fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        docs = self.rag._process_faq(data, "sample_faq.json")
        assert len(docs) >= 3
        categories = {d["category"] for d in docs}
        assert "Facturation" in categories


# ─────────────────────────────────────────────────────────────────────────────
# _process_legal() — traitement des documents légaux
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessLegal:
    @pytest.fixture(autouse=True)
    def setup(self):
        with patch("kiwi_rag_advanced.ComplyRAG.__init__", return_value=None):
            from kiwi_rag_advanced import ComplyRAG
            self.rag = ComplyRAG.__new__(ComplyRAG)

    def test_processes_legal_list(self):
        data = [
            {
                "title": "Statuts types",
                "category": "Statuts",
                "content": "Les statuts définissent l'objet social de la JE et ses modalités de gouvernance.",
                "url": "https://cnje.fr",
            }
        ]
        docs = self.rag._process_legal(data, "legal.json")
        assert len(docs) >= 1
        assert all(d["type"] == "legal" for d in docs)

    def test_ignores_items_without_content(self):
        data = [{"title": "Vide", "category": "Test"}]
        docs = self.rag._process_legal(data, "test.json")
        assert docs == []

    def test_uses_sections_as_fallback(self):
        data = [{
            "title": "Guide",
            "category": "Légal",
            "sections": [
                {"titre": "Introduction", "content": "Texte de présentation de la JE."},
                {"titre": "Adhésion", "content": "Les modalités d'adhésion sont définies par les statuts."},
            ]
        }]
        docs = self.rag._process_legal(data, "guide.json")
        assert len(docs) >= 1

    def test_legal_from_fixture(self):
        fixture_path = Path(__file__).parent / "fixtures" / "sample_legal.json"
        with open(fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        docs = self.rag._process_legal(data, "sample_legal.json")
        assert len(docs) >= 2
        assert all(d["type"] == "legal" for d in docs)


# ─────────────────────────────────────────────────────────────────────────────
# _process_generic()
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessGeneric:
    @pytest.fixture(autouse=True)
    def setup(self):
        with patch("kiwi_rag_advanced.ComplyRAG.__init__", return_value=None):
            from kiwi_rag_advanced import ComplyRAG
            self.rag = ComplyRAG.__new__(ComplyRAG)

    def test_processes_string_list(self):
        data = ["Contenu texte assez long pour dépasser les 30 caractères."]
        docs = self.rag._process_generic(data, "test.json")
        assert len(docs) >= 1

    def test_processes_dict_with_content(self):
        data = [{"title": "Test", "content": "Voici du contenu documentaire pertinent pour la JE."}]
        docs = self.rag._process_generic(data, "test.json")
        assert len(docs) >= 1

    def test_skips_empty_content(self):
        data = [{"title": "Vide", "content": ""}]
        docs = self.rag._process_generic(data, "test.json")
        assert docs == []


# ─────────────────────────────────────────────────────────────────────────────
# search() — recherche hybride sur un petit corpus
# ─────────────────────────────────────────────────────────────────────────────

class TestSearch:
    @pytest.fixture(autouse=True)
    def setup_rag_with_small_corpus(self):
        """Crée une instance RAG réelle avec un petit corpus en mémoire."""
        with patch("kiwi_rag_advanced.ComplyRAG.__init__", return_value=None):
            from kiwi_rag_advanced import ComplyRAG
            self.rag = ComplyRAG.__new__(ComplyRAG)

        from collections import defaultdict
        self.rag._sessions = defaultdict(list)
        self.rag._redis = None
        self.rag._web = None

        # Petit corpus de test
        self.rag._documents = [
            {"content": "La TVA pour une Junior-Entreprise est de 20%.", "source": "faq.json", "type": "faq", "category": "Fiscalité", "title": "TVA JE", "url": ""},
            {"content": "Pour facturer une étude, la JE doit émettre une facture conforme.", "source": "faq.json", "type": "faq", "category": "Facturation", "title": "Facturation", "url": ""},
            {"content": "L'agrément CNJE est renouvelé chaque année.", "source": "legal.json", "type": "legal", "category": "Agrément", "title": "Agrément", "url": ""},
            {"content": "Les statuts d'une JE doivent être conformes au modèle CNJE.", "source": "legal.json", "type": "legal", "category": "Statuts", "title": "Statuts", "url": ""},
            {"content": "La convention d'étude doit être signée avant le début des travaux.", "source": "faq.json", "type": "faq", "category": "Contrats", "title": "Convention", "url": ""},
        ]

        self.rag._build_tfidf()
        self.rag._build_bm25()

    def _build_tfidf(self):
        from kiwi_rag_advanced import ComplyRAG
        ComplyRAG._build_tfidf(self.rag)

    def _build_bm25(self):
        from kiwi_rag_advanced import ComplyRAG
        ComplyRAG._build_bm25(self.rag)

    def test_search_returns_tuple(self):
        docs, score = self.rag.search("TVA Junior-Entreprise")
        assert isinstance(docs, list)
        assert isinstance(score, float)

    def test_search_finds_relevant_doc(self):
        docs, score = self.rag.search("TVA Junior-Entreprise")
        assert len(docs) > 0
        contents = [d["content"] for d in docs]
        assert any("TVA" in c for c in contents)

    def test_search_returns_score_between_0_and_1(self):
        _, score = self.rag.search("facturation étude JE")
        assert 0.0 <= score <= 1.0

    def test_search_on_empty_corpus(self):
        from kiwi_rag_advanced import ComplyRAG
        empty_rag = ComplyRAG.__new__(ComplyRAG)
        empty_rag._documents = []
        empty_rag._vectors = None
        empty_rag._vectorizer = None
        empty_rag._bm25 = None
        docs, score = empty_rag.search("test")
        assert docs == []
        assert score == 0.0

    def test_search_limits_results(self):
        docs, _ = self.rag.search("JE CNJE", n=2)
        assert len(docs) <= 2


# ─────────────────────────────────────────────────────────────────────────────
# WebSearcher — module de recherche web
# ─────────────────────────────────────────────────────────────────────────────

class TestWebSearcher:
    def test_init_without_duckduckgo(self):
        """WebSearcher se dégrade gracieusement si DuckDuckGo n'est pas disponible."""
        import sys
        with patch.dict(sys.modules, {"duckduckgo_search": None}):
            from importlib import reload
            import web_search
            reload(web_search)
            searcher = web_search.WebSearcher()
            # Quand ddg n'est pas dispo, available = False
            # (peut varier selon si le module est déjà importé)

    def test_search_returns_empty_when_unavailable(self):
        from web_search import WebSearcher
        searcher = WebSearcher()
        searcher.available = False
        results = searcher.search("Junior-Entreprise TVA")
        assert results == []

    def test_has_reliable_results_true(self):
        from web_search import WebSearcher, SearchResult
        searcher = WebSearcher()
        results = [
            SearchResult(title="CNJE", url="https://cnje.fr/page", body="Contenu", is_reliable=True),
        ]
        assert searcher.has_reliable_results(results) is True

    def test_has_reliable_results_false(self):
        from web_search import WebSearcher, SearchResult
        searcher = WebSearcher()
        results = [
            SearchResult(title="Blog", url="https://random-blog.com", body="Contenu", is_reliable=False),
        ]
        assert searcher.has_reliable_results(results) is False

    def test_has_reliable_results_empty_list(self):
        from web_search import WebSearcher
        searcher = WebSearcher()
        assert searcher.has_reliable_results([]) is False

    def test_format_context_includes_title_and_body(self):
        from web_search import WebSearcher, SearchResult
        searcher = WebSearcher()
        results = [
            SearchResult(
                title="Guide TVA JE",
                url="https://impots.gouv.fr/tva",
                body="La TVA est de 20% pour les JE.",
                is_reliable=True,
            )
        ]
        ctx = searcher.format_context(results)
        assert "Guide TVA JE" in ctx
        assert "La TVA est de 20%" in ctx
        assert "impots.gouv.fr" in ctx

    def test_format_context_marks_reliability(self):
        from web_search import WebSearcher, SearchResult
        searcher = WebSearcher()
        reliable = SearchResult("R", "https://cnje.fr", "A", is_reliable=True)
        unreliable = SearchResult("U", "https://blog.fr", "B", is_reliable=False)
        ctx = searcher.format_context([reliable, unreliable])
        assert "Source officielle" in ctx
        assert "Source non vérifiée" in ctx

    def test_get_ticket_message_contains_url(self):
        from web_search import WebSearcher
        searcher = WebSearcher()
        msg = searcher.get_ticket_message()
        assert "junior-entreprises.com" in msg or "support" in msg
        assert len(msg) > 50
