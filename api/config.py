import os
from dotenv import load_dotenv

load_dotenv()

# Claude API
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

# Mistral API
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")

# Modèles supportés
MISTRAL_MODELS = {"mistral-large-latest", "mistral-small-latest", "open-mistral-7b"}
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "4096"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.1"))

# RAG settings
DATA_DIR = os.getenv("DATA_DIR", "./data")
VECTOR_DB_PATH = os.getenv("VECTOR_DB_PATH", "./chroma_db")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
MAX_CONTEXT_DOCS = int(os.getenv("MAX_CONTEXT_DOCS", "6"))
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.35"))

# Embedding
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

# Web search fallback
ENABLE_WEB_SEARCH = os.getenv("ENABLE_WEB_SEARCH", "true").lower() == "true"
WEB_SEARCH_MAX_RESULTS = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))
TRUSTED_DOMAINS = [
    "junior-entreprises.com",
    "cnje.fr",
    "legifrance.gouv.fr",
    "service-public.fr",
    "urssaf.fr",
    "travail-emploi.gouv.fr",
    "economie.gouv.fr",
    "ameli.fr",
    "impots.gouv.fr",
    "bofip.impots.gouv.fr",
    "senat.fr",
    "assemblee-nationale.fr",
    "bpifrance.fr",
]

# CNJE ticket
CNJE_TICKET_URL = os.getenv(
    "CNJE_TICKET_URL",
    "https://support.junior-entreprises.com/hc/fr/requests/new"
)

# File type detection
KIWI_FILE_TYPES = {
    "kiwi-legal": "legal",
    "legal": "legal",
    "faq": "faq",
    "junior": "je",
    "base-je": "je",
    "rse": "rse",
    "formation": "formation",
    "services": "services",
    "kiwi_rse": "rse",
}
