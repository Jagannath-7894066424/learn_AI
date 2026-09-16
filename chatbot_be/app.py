"""FastAPI backend for the RAG chatbot.

Run with:  uvicorn app:app --reload --port 8000
Interactive API docs:  http://localhost:8000/docs

Error handling: rag.py raises typed errors; the exception handlers below turn
them into the right HTTP status, so every endpoint returns a useful message
instead of a bare 500.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import rag

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Make sure the table, extension and upload folder exist before serving."""
    try:
        rag.init_schema()
    except rag.RagError:
        # Don't crash on boot — /api/health should still answer and say what's wrong.
        logger.exception("Schema initialisation failed at startup; the API will start anyway")
    try:
        rag.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.exception("Could not create the upload directory %s", rag.UPLOAD_DIR)
    yield


app = FastAPI(title="RAG Chatbot API", version="1.0.0", lifespan=lifespan)

# The React dev server runs on a different origin, so it needs CORS.
# Vite picks the next free port when 5173 is taken (5174, 5175, ...), so match
# any localhost port rather than pinning one.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# Exception handlers — one place to map error type -> HTTP status
# --------------------------------------------------------------------------
@app.exception_handler(rag.ConfigError)
async def handle_config_error(_request: Request, exc: rag.ConfigError):
    """Misconfiguration (missing API key, wrong dimension) -> 503."""
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(rag.DatabaseError)
async def handle_database_error(_request: Request, exc: rag.DatabaseError):
    """Postgres unreachable or query failed -> 503."""
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(rag.LLMError)
async def handle_llm_error(_request: Request, exc: rag.LLMError):
    """The provider is reachable but failed -> 502 (bad upstream)."""
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(rag.RagError)
async def handle_rag_error(_request: Request, exc: rag.RagError):
    """Anything else from the RAG core (embedding failures included) -> 500."""
    logger.exception("Unhandled RAG error")
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------
class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(rag.TOP_K, ge=1, le=20)


class Source(BaseModel):
    source: str
    snippet: str
    distance: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.get("/api/health")
def health():
    """Provider info plus how much is indexed — used by the UI status bar.

    Never raises: if the database is down it reports that instead, so the UI
    can show a useful status rather than "backend offline".
    """
    provider = rag.LLM_PROVIDER
    info = {
        "status": "ok",
        "provider": provider,
        "model": rag.GROQ_MODEL if provider == "groq" else rag.OLLAMA_MODEL,
        "llm_ready": bool(rag.GROQ_API_KEY) if provider == "groq" else True,
        "documents": 0,
        "chunks": 0,
    }
    try:
        with rag.connect() as conn:
            info["chunks"] = rag.count_chunks(conn)
            info["documents"] = len(rag.list_sources(conn))
    except rag.RagError as exc:
        logger.warning("Health check could not reach the database: %s", exc)
        info["status"] = "degraded"
        info["error"] = str(exc)
    except Exception as exc:
        logger.exception("Unexpected error during health check")
        info["status"] = "degraded"
        info["error"] = f"Unexpected error: {exc}"
    return info


@app.get("/api/documents")
def get_documents():
    """List every indexed source with its chunk count."""
    try:
        with rag.connect() as conn:
            sources = rag.list_sources(conn)
    except rag.RagError:
        raise                                   # handled above -> 503
    except Exception as exc:
        logger.exception("Unexpected error listing documents")
        raise HTTPException(status_code=500, detail=f"Could not list documents: {exc}") from exc

    return {"documents": [{"source": source, "chunks": count} for source, count in sources]}


@app.post("/api/documents/upload")
async def upload_documents(files: list[UploadFile] = File(...)):
    """Accept .txt/.md/.pdf/.xlsx/.csv uploads, extract text, then chunk + embed + store.

    One bad file does not fail the batch: it lands in `skipped` with a reason,
    and the good files are still indexed.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files were uploaded.")

    try:
        rag.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.exception("Could not create the upload directory")
        raise HTTPException(status_code=500, detail=f"Could not create the upload folder: {exc}") from exc

    results, skipped = [], []

    with rag.connect() as conn:
        for upload in files:
            name = Path(upload.filename or "").name  # strip any path components
            if not name or Path(name).suffix.lower() not in rag.SUFFIXES:
                skipped.append({"filename": upload.filename, "reason": "only .txt and .md are supported"})
                continue

            # --- read ---
            try:
                raw = await upload.read()
            except Exception as exc:
                logger.exception("Could not read the uploaded file %r", name)
                skipped.append({"filename": name, "reason": f"could not read the upload: {exc}"})
                continue
            finally:
                await upload.close()

            if not raw:
                skipped.append({"filename": name, "reason": "file is empty"})
                continue

            # --- extract text (PDF / Excel / CSV / plain) ---
            try:
                text = rag.extract_text(raw, name)
            except rag.ExtractionError as exc:
                # A file we cannot read shouldn't fail the whole batch.
                logger.info("Could not extract %s: %s", name, exc)
                skipped.append({"filename": name, "reason": str(exc)})
                continue

            # --- save ---
            dest = rag.UPLOAD_DIR / name
            try:
                # Save the ORIGINAL bytes so the CLI can re-ingest it later.
                # PDFs and workbooks are binary, so never write the decoded text.
                dest.write_bytes(raw)
            except OSError as exc:
                logger.exception("Could not save %s", dest)
                skipped.append({"filename": name, "reason": f"could not save the file: {exc}"})
                continue

            # --- index ---
            try:
                source = str(dest.relative_to(rag.ROOT_DIR))
            except ValueError:
                source = str(dest)

            try:
                chunks = rag.store_document(conn, source, text)
            except rag.RagError as exc:
                # Keep going with the rest of the batch, but report this one.
                logger.exception("Could not index %s", source)
                skipped.append({"filename": name, "reason": str(exc)})
                continue

            if chunks == 0:
                skipped.append({"filename": name, "reason": "file has no usable text"})
            else:
                results.append({"source": source, "chunks": chunks})

    if not results and skipped:
        raise HTTPException(status_code=400, detail={"message": "Nothing was ingested", "skipped": skipped})
    return {"ingested": results, "skipped": skipped}


@app.delete("/api/documents")
def delete_document(source: str):
    """Remove one source's chunks from the index (the saved file is kept)."""
    if not source.strip():
        raise HTTPException(status_code=400, detail="A source must be given.")

    try:
        with rag.connect() as conn:
            deleted = rag.delete_source(conn, source)
    except rag.RagError:
        raise                                   # handled above -> 503
    except Exception as exc:
        logger.exception("Unexpected error deleting %r", source)
        raise HTTPException(status_code=500, detail=f"Could not delete {source!r}: {exc}") from exc

    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"No indexed chunks for source {source!r}")
    return {"source": source, "deleted": deleted}


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """Retrieve the nearest chunks and answer strictly from them."""
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="The question cannot be blank.")

    try:
        with rag.connect() as conn:
            if rag.count_chunks(conn) == 0:
                raise HTTPException(status_code=400, detail="No documents indexed yet — upload one first.")
            rows = rag.retrieve(conn, question, k=request.top_k)
    except HTTPException:
        raise                                   # don't rewrap our own 400
    except rag.RagError:
        raise                                   # handled above -> 502/503
    except Exception as exc:
        logger.exception("Unexpected error during retrieval")
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {exc}") from exc

    if not rows:
        return ChatResponse(answer="I don't know based on the provided documents.", sources=[])

    try:
        answer = rag.llm_answer(question, rag.build_context(rows))
    except rag.RagError:
        raise                                   # handled above -> 502/503
    except Exception as exc:
        logger.exception("Unexpected error calling the LLM")
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc

    try:
        sources = [
            Source(source=source, snippet=content[:300], distance=float(distance))
            for content, source, distance in rows
        ]
    except (TypeError, ValueError) as exc:
        logger.exception("Malformed retrieval rows")
        raise HTTPException(status_code=500, detail=f"Malformed search results: {exc}") from exc

    return ChatResponse(answer=answer, sources=sources)
