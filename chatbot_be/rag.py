"""Shared core for the RAG chatbot: config, Postgres/pgvector, embeddings, LLM.

Used by both the CLI scripts (ingest.py, chat.py) and the HTTP API (app.py),
so retrieval and chunking behave identically no matter how you drive them.

Error handling: every function guards its work and raises one of the typed
errors below. Nothing is swallowed silently — failures are logged with a
stack trace and re-raised so the caller can map them to an HTTP status.
"""

import logging
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector

from extractors import SUPPORTED, ExtractionError, extract_text  # noqa: F401  (re-exported)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Typed errors — let callers react to the *kind* of failure
# --------------------------------------------------------------------------
class RagError(Exception):
    """Base class for every error raised by this module."""


class ConfigError(RagError):
    """Missing or invalid configuration (e.g. no API key)."""


class DatabaseError(RagError):
    """Postgres is unreachable or a query failed."""


class EmbeddingError(RagError):
    """The embedding model failed to load or encode."""


class LLMError(RagError):
    """The LLM provider was unreachable or returned something unusable."""


BASE_DIR = Path(__file__).resolve().parent   # chatbot_be/
ROOT_DIR = BASE_DIR.parent                   # repository root

# Load chatbot_be/.env explicitly so it works regardless of the current directory.
try:
    load_dotenv(BASE_DIR / ".env")
except Exception:
    # A malformed .env should warn, not kill the process — defaults still apply.
    logger.warning("Could not read %s; falling back to defaults", BASE_DIR / ".env", exc_info=True)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://raguser:ragpass@localhost:55432/ragdb")
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

try:
    EMBED_DIM = int(os.getenv("EMBED_DIM", "384"))
except ValueError:
    logger.warning("EMBED_DIM=%r is not an integer; using 384", os.getenv("EMBED_DIM"))
    EMBED_DIM = 384

# Where documents live. Uploads from the web UI land in DOCS_DIR/uploads.
DOCS_DIR = Path(os.getenv("DOCS_DIR", ROOT_DIR / "docs"))
UPLOAD_DIR = DOCS_DIR / "uploads"

CHUNK_SIZE = 800      # characters per chunk
CHUNK_OVERLAP = 150   # characters repeated between consecutive chunks
SUFFIXES = set(SUPPORTED)   # .txt .md .pdf .xlsx .xlsm .csv — see extractors.py
TOP_K = 4             # chunks fed to the model per question


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
def connect(register_types: bool = True) -> psycopg.Connection:
    """Open a psycopg (v3) connection and teach it about the pgvector type."""
    try:
        conn = psycopg.connect(DATABASE_URL)
    except psycopg.OperationalError as exc:
        logger.error("Cannot reach Postgres at %s", DATABASE_URL.split("@")[-1], exc_info=True)
        raise DatabaseError(
            f"Cannot connect to the database ({exc}). Is the container running? "
            "Check `docker compose ps` and DATABASE_URL in .env."
        ) from exc
    except psycopg.Error as exc:
        logger.error("Unexpected database error while connecting", exc_info=True)
        raise DatabaseError(f"Database connection failed: {exc}") from exc

    if register_types:
        try:
            register_vector(conn)
        except psycopg.Error:
            # The extension does not exist yet — init_schema() creates it.
            logger.debug("pgvector type not registered yet; init_schema() will create it")
            conn.rollback()
        except Exception:
            conn.close()
            logger.error("Failed to register the pgvector type", exc_info=True)
            raise DatabaseError("Could not register the pgvector type on the connection")
    return conn


def init_schema() -> None:
    """Create the vector extension, the documents table and the HNSW index."""
    try:
        with connect(register_types=False) as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                conn.commit()

                register_vector(conn)  # safe now that the type exists

                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS documents (
                        id        BIGSERIAL PRIMARY KEY,
                        content   TEXT NOT NULL,
                        source    TEXT NOT NULL,
                        embedding VECTOR({EMBED_DIM}) NOT NULL
                    )
                    """
                )
                # HNSW + cosine distance, matching the "<=>" operator used at query time.
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS documents_embedding_idx
                    ON documents USING hnsw (embedding vector_cosine_ops)
                    """
                )
                cur.execute("CREATE INDEX IF NOT EXISTS documents_source_idx ON documents (source)")
            conn.commit()
    except DatabaseError:
        raise                                   # already logged and typed
    except psycopg.errors.InsufficientPrivilege as exc:
        logger.error("Database user lacks privileges to create the extension", exc_info=True)
        raise DatabaseError(
            "The database user may not CREATE EXTENSION. Grant superuser or install pgvector manually."
        ) from exc
    except psycopg.Error as exc:
        logger.error("Schema initialisation failed", exc_info=True)
        raise DatabaseError(f"Could not initialise the schema: {exc}") from exc


def list_sources(conn):
    """Return [(source, chunk_count), ...] for everything currently indexed."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT source, count(*) FROM documents GROUP BY source ORDER BY source")
            return cur.fetchall()
    except psycopg.Error as exc:
        logger.error("Could not list sources", exc_info=True)
        raise DatabaseError(f"Could not list documents: {exc}") from exc


def delete_source(conn, source: str) -> int:
    """Remove every chunk belonging to `source`. Returns rows deleted."""
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM documents WHERE source = %s", (source,))
            deleted = cur.rowcount
        conn.commit()
        return deleted
    except psycopg.Error as exc:
        conn.rollback()
        logger.error("Could not delete source %r", source, exc_info=True)
        raise DatabaseError(f"Could not delete {source!r}: {exc}") from exc


def count_chunks(conn) -> int:
    """Total number of indexed chunks."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM documents")
            return cur.fetchone()[0]
    except psycopg.Error as exc:
        logger.error("Could not count chunks", exc_info=True)
        raise DatabaseError(f"Could not count documents: {exc}") from exc


# --------------------------------------------------------------------------
# Embeddings
# --------------------------------------------------------------------------
_model = None  # loaded lazily, so importing this module stays cheap


def get_model():
    """Return the shared SentenceTransformer instance (downloaded on first use)."""
    global _model
    if _model is not None:
        return _model

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        logger.error("sentence-transformers is not installed", exc_info=True)
        raise EmbeddingError(
            "sentence-transformers is not installed. Run: pip install -r requirements.txt"
        ) from exc

    try:
        model = SentenceTransformer(EMBED_MODEL)
    except Exception as exc:
        # Usually a download failure on first run (no network / HF unreachable).
        logger.error("Could not load embedding model %s", EMBED_MODEL, exc_info=True)
        raise EmbeddingError(
            f"Could not load the embedding model {EMBED_MODEL!r}: {exc}. "
            "The first run needs internet access to download it."
        ) from exc

    try:
        # Method was renamed in newer sentence-transformers; support both.
        get_dim = getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension
        dim = get_dim()
    except Exception:
        logger.warning("Could not determine the model's dimension; skipping the check", exc_info=True)
        dim = EMBED_DIM

    if dim != EMBED_DIM:
        raise ConfigError(
            f"EMBED_DIM is {EMBED_DIM} but {EMBED_MODEL} produces {dim}-dim vectors. "
            "Update EMBED_DIM and recreate the documents table."
        )

    _model = model
    return _model


def embed(texts):
    """Embed a string or list of strings. Returns a (n, EMBED_DIM) numpy array.

    Embeddings are L2-normalised, which makes cosine distance cheap and stable.
    """
    if isinstance(texts, str):
        texts = [texts]
    texts = list(texts)
    if not texts:
        raise EmbeddingError("Nothing to embed — the text list is empty.")

    try:
        return get_model().encode(texts, normalize_embeddings=True, show_progress_bar=False)
    except RagError:
        raise                                   # already typed by get_model()
    except Exception as exc:
        logger.error("Embedding failed for %d text(s)", len(texts), exc_info=True)
        raise EmbeddingError(f"Could not embed the text: {exc}") from exc


# --------------------------------------------------------------------------
# Chunking + storage
# --------------------------------------------------------------------------
def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """Split text into ~`size`-character chunks that overlap by `overlap`.

    Chunks are cut at the last whitespace before the limit where possible, so
    words are not split in half.
    """
    if not isinstance(text, str):
        raise RagError(f"chunk_text expected a string, got {type(text).__name__}")
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ConfigError(f"Invalid chunking settings: size={size}, overlap={overlap}")

    try:
        text = text.strip()
        if not text:
            return []

        chunks = []
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            if end < len(text):
                # Back off to the last whitespace, but never shrink below half a chunk.
                split = text.rfind(" ", start + size // 2, end)
                if split != -1:
                    end = split
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)  # step forward, keeping the overlap
        return chunks
    except RagError:
        raise
    except Exception as exc:
        logger.error("Chunking failed", exc_info=True)
        raise RagError(f"Could not split the document into chunks: {exc}") from exc


def store_document(conn, source: str, text: str) -> int:
    """Chunk, embed and store one document. Returns the number of chunks stored.

    Re-storing the same source replaces its chunks instead of duplicating them.
    The delete and the insert share one transaction, so a failure mid-way leaves
    the previous version of the document intact.
    """
    chunks = chunk_text(text)
    if not chunks:
        return 0

    vectors = embed(chunks)  # one batched embedding call per document

    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM documents WHERE source = %s", (source,))
            cur.executemany(
                "INSERT INTO documents (content, source, embedding) VALUES (%s, %s, %s)",
                [(chunk, source, vector) for chunk, vector in zip(chunks, vectors)],
            )
        conn.commit()
        return len(chunks)
    except psycopg.Error as exc:
        conn.rollback()   # keep the old chunks rather than half-replacing them
        logger.error("Could not store %d chunks for %r", len(chunks), source, exc_info=True)
        raise DatabaseError(f"Could not store {source!r}: {exc}") from exc


# --------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------
def retrieve(conn, question: str, k: int = TOP_K):
    """Return the k nearest chunks as (content, source, distance) tuples.

    "<=>" is pgvector's cosine distance operator: 0 = identical, 2 = opposite.
    """
    if not question or not question.strip():
        raise RagError("Cannot retrieve for an empty question.")
    if k <= 0:
        raise ConfigError(f"top_k must be positive, got {k}")

    query_vector = embed(question)[0]

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT content, source, embedding <=> %s AS distance
                FROM documents
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                (query_vector, query_vector, k),
            )
            return cur.fetchall()
    except psycopg.errors.UndefinedTable as exc:
        logger.error("The documents table does not exist", exc_info=True)
        raise DatabaseError("The documents table does not exist yet — ingest something first.") from exc
    except psycopg.Error as exc:
        logger.error("Vector search failed", exc_info=True)
        raise DatabaseError(f"Search failed: {exc}") from exc


def build_context(rows) -> str:
    """Format retrieved chunks into a single numbered context block."""
    try:
        return "\n\n".join(
            f"[{i}] (source: {source})\n{content}"
            for i, (content, source, _distance) in enumerate(rows, start=1)
        )
    except (TypeError, ValueError) as exc:
        logger.error("Malformed retrieval rows passed to build_context", exc_info=True)
        raise RagError(f"Could not build the context block: {exc}") from exc


# --------------------------------------------------------------------------
# LLM
# --------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a precise assistant. Answer the user's question using ONLY the "
    "context provided. If the context does not contain the answer, say "
    '"I don\'t know based on the provided documents." '
    "Never invent facts and never rely on outside knowledge. Keep answers concise."
)


def _answer_with_groq(messages) -> str:
    """Call the Groq API. Raises ConfigError/LLMError on failure."""
    try:
        from groq import Groq
    except ImportError as exc:
        raise EmbeddingError("The groq package is not installed. Run: pip install -r requirements.txt") from exc

    if not GROQ_API_KEY:
        raise ConfigError("LLM_PROVIDER=groq but GROQ_API_KEY is not set in chatbot_be/.env")

    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=GROQ_MODEL, messages=messages, temperature=0.2
        )
    except Exception as exc:
        name = type(exc).__name__
        # Authentication / rate limit / bad model name all surface here.
        if "Authentication" in name or "401" in str(exc):
            raise ConfigError(f"Groq rejected the API key: {exc}") from exc
        if "RateLimit" in name or "429" in str(exc):
            raise LLMError(f"Groq rate limit reached — wait a moment and retry: {exc}") from exc
        logger.error("Groq request failed", exc_info=True)
        raise LLMError(f"Groq request failed: {exc}") from exc

    try:
        message = response.choices[0].message
        answer = (message.content or "").strip()
    except (AttributeError, IndexError, TypeError) as exc:
        logger.error("Unexpected Groq response shape: %r", response, exc_info=True)
        raise LLMError("Groq returned an unexpected response shape.") from exc

    if not answer:
        # Reasoning models (gpt-oss-*) can spend the whole budget on reasoning
        # tokens and return empty content.
        logger.error("Groq returned empty content for model %s", GROQ_MODEL)
        raise LLMError(
            f"{GROQ_MODEL} returned an empty answer (the token budget may have gone to "
            "reasoning). Try a different GROQ_MODEL."
        )
    return answer


def _answer_with_ollama(messages) -> str:
    """Call the local Ollama daemon. Raises ConfigError/LLMError on failure."""
    try:
        import ollama
    except ImportError as exc:
        raise EmbeddingError("The ollama package is not installed. Run: pip install -r requirements.txt") from exc

    try:
        response = ollama.chat(model=OLLAMA_MODEL, messages=messages, options={"temperature": 0.2})
    except Exception as exc:
        text = str(exc).lower()
        if "connection" in text or "refused" in text:
            raise LLMError(
                f"Cannot reach Ollama — is the daemon running? ({exc})"
            ) from exc
        if "not found" in text or "no such model" in text:
            raise ConfigError(
                f"Model {OLLAMA_MODEL!r} is not pulled. Run: ollama pull {OLLAMA_MODEL}"
            ) from exc
        logger.error("Ollama request failed", exc_info=True)
        raise LLMError(f"Ollama request failed: {exc}") from exc

    try:
        return response["message"]["content"].strip()
    except (KeyError, TypeError, AttributeError) as exc:
        logger.error("Unexpected Ollama response shape: %r", response, exc_info=True)
        raise LLMError("Ollama returned an unexpected response shape.") from exc


def llm_answer(question: str, context: str) -> str:
    """Answer `question` from `context`, routing to Groq or Ollama per LLM_PROVIDER."""
    if not question or not question.strip():
        raise RagError("Cannot answer an empty question.")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"},
    ]

    if LLM_PROVIDER == "groq":
        return _answer_with_groq(messages)
    if LLM_PROVIDER == "ollama":
        return _answer_with_ollama(messages)
    raise ConfigError(f"Unknown LLM_PROVIDER={LLM_PROVIDER!r}. Use 'ollama' or 'groq'.")
