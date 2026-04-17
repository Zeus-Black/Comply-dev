import os
from dotenv import load_dotenv

load_dotenv()

# Claude API
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

# Mistral API
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_MODELS = {"open-mistral-7b", "open-mixtral-8x7b", "open-mixtral-8x22b"}

# DeepSeek API (compatible OpenAI)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODELS = {"deepseek-chat", "deepseek-reasoner"}

# Gemini API (compatible OpenAI)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_MODELS = {"gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"}

# Groq API (compatible OpenAI)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODELS = {"llama-3.3-70b-versatile", "llama-3.1-8b-instant", "qwen-qwq-32b"}
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

# Redis cache
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CACHE_TTL = int(os.getenv("CACHE_TTL", str(7 * 24 * 3600)))  # 7 jours par défaut

# CNJE ticket
CNJE_TICKET_URL = os.getenv(
    "CNJE_TICKET_URL",
    "https://support.junior-entreprises.com/hc/fr/requests/new"
)

# Notion
NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
NOTION_PAGE_IDS = [x.strip() for x in os.getenv("NOTION_PAGE_IDS", "").split(",") if x.strip()]
NOTION_DATABASE_IDS = [x.strip() for x in os.getenv("NOTION_DATABASE_IDS", "").split(",") if x.strip()]

# Google Drive
GOOGLE_DRIVE_SERVICE_ACCOUNT = os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT", "")  # JSON string
GOOGLE_DRIVE_TOKEN_FILE = os.getenv("GOOGLE_DRIVE_TOKEN_FILE", "")             # path to token.json
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
GOOGLE_DRIVE_SHARED_DRIVE_ID = os.getenv("GOOGLE_DRIVE_SHARED_DRIVE_ID", "")

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
    "notion": "general",
    "drive": "general",
}
