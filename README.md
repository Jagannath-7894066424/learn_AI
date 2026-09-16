# run_gpt2 demo

This project includes a small runner to load `openai-community/gpt2` from the Hugging Face Hub and generate text.

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the demo:

```bash
python3 run_gpt2.py "Once upon a time"
```

Notes:
- The first run downloads the model from the Hub and may take a while.
- If you have a GPU and an appropriate PyTorch build, the script will use it automatically.

---

# RAG chatbot (pgvector + local embeddings)

A document Q&A app with a **React UI** and a **FastAPI backend**. It answers
questions using **only** your own documents. Everything is free and local:
embeddings run on your machine, vectors live in Postgres via pgvector, and the
LLM is either local Ollama or the free Groq API.

```
chatbot_be/  FastAPI + RAG core (rag.py, app.py, ingest.py, chat.py)
chatbot_ui/  React + Vite UI (Upload page, Chat page)
docs/        your documents; UI uploads land in docs/uploads/
docker-compose.yml   Postgres 16 + pgvector
```

| Piece | What it uses |
| --- | --- |
| Embeddings | `all-MiniLM-L6-v2`, 384 dimensions, no API key |
| Vector store | PostgreSQL 16 + pgvector, HNSW index, cosine distance |
| LLM | `groq` (free API) or `ollama` (fully local) |
| API | FastAPI on port 8000 |
| UI | React 18 + Vite on port 5173 |

## Prerequisites

- Python 3.10+, Node 18+
- Docker with Docker Compose
- A free Groq key (https://console.groq.com/keys) **or** [Ollama](https://ollama.com/download) installed

## Setup

```bash
# 1. Python dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r chatbot_be/requirements.txt

# 2. Postgres + pgvector
docker compose up -d
docker compose ps            # wait for "healthy"

# 3. Config
cp chatbot_be/.env.example chatbot_be/.env   # already done if chatbot_be/.env exists

# 4. Frontend dependencies
cd chatbot_ui && npm install && cd ..
```

Then set your LLM provider in `chatbot_be/.env`:

- **Groq:** `LLM_PROVIDER=groq` and `GROQ_API_KEY=gsk_...`
- **Ollama:** `LLM_PROVIDER=ollama`, then `ollama pull llama3.2`

## Run

Two terminals, both from the project root:

```bash
# Terminal 1 — backend
source .venv/bin/activate
cd chatbot_be && uvicorn app:app --reload --port 8000
```

```bash
# Terminal 2 — frontend
cd chatbot_ui && npm run dev
```

Open **http://localhost:5173**. API docs are at http://localhost:8000/docs.

The **Upload** page takes `.txt`/`.md` files by drag-and-drop and shows what is
indexed; the **Chat** page answers questions and shows which chunks it used.

### Command line alternative

The CLI scripts share the same code as the API:

```bash
cd chatbot_be
python ingest.py             # ingest ../docs
python ingest.py notes.md    # or specific files/folders
python chat.py               # terminal chat
```

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | provider, model, and how much is indexed |
| GET | `/api/documents` | list indexed sources + chunk counts |
| POST | `/api/documents/upload` | multipart upload, chunk + embed + store |
| DELETE | `/api/documents?source=...` | remove one source from the index |
| POST | `/api/chat` | `{question}` -> `{answer, sources}` |

## How it works

Each document is split into ~800-character chunks with 150 characters of
overlap, embedded in one batched call, and stored in the `documents` table.
A question is embedded the same way, and the 4 nearest chunks are found with
pgvector's `<=>` cosine-distance operator. Only those chunks go to the LLM,
with instructions to answer from them alone — if the answer isn't in your
documents, it says so. Re-uploading a file replaces its chunks rather than
duplicating them.

## Notes & troubleshooting

- **Host port is 55432, not 5432.** This machine already runs a system PostgreSQL
  (cluster `12/main` on 5433, with 5432/5434 also occupied), so the container
  publishes `55432:5432` and `DATABASE_URL` uses port 55432. If you move it, change
  both [docker-compose.yml](docker-compose.yml) and `DATABASE_URL` in `chatbot_be/.env`.
- The first ingest downloads the embedding model (~90 MB) from Hugging Face.
- The vector column is `VECTOR(384)` to match the model. If you switch models,
  update `EMBED_DIM` in `chatbot_be/.env` **and** `DROP TABLE documents;` so it is
  recreated with the new dimension.
- *Connection refused* — Postgres is still starting; check `docker compose ps`.
  Plain `docker compose ps` hides non-running containers; use `-a` to see one that
  was created but failed to start (usually a port conflict).
- *password authentication failed for user "raguser"* — you reached the system
  Postgres instead of the container. Check the port in `DATABASE_URL`.
- *"backend offline" in the UI header* — the FastAPI server isn't running on port 8000.
