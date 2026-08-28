# Cookbook RAG API — Setup Notes

FastAPI backend for a RAG pipeline over a cookbook PDF, using Pinecone for
vector storage and Postgres (`swish_db`) for chat/document logging.

## What was built

```
cookbook-backend/
├── app/
│   ├── main.py         # FastAPI app, lifespan hook that runs init_db()
│   ├── routes.py        # POST /upload, POST /ingest, POST /query, GET /health
│   ├── rag.py            # get_llm() provider factory, ingest_*(), answer_question()
│   ├── loader.py         # Text extraction for any document type
│   ├── ocr.py            # Gemini transcription for images and scanned PDFs
│   ├── chunking.py       # plain character-based chunker (no framework)
│   ├── vectorstore.py    # raw OpenAI embeddings + raw Pinecone upsert/query
│   ├── prompt.py         # plain system prompt + prompt string builder
│   ├── config.py         # pydantic-settings Settings, reads .env
│   └── database.py       # SQLModel engine/session, ChatLog + DocumentRecord tables
├── documents/             # put cookbook.pdf here (empty — none existed to copy)
├── vector_db/             # kept per requested structure; unused now (vectors live in Pinecone)
├── requirements.txt
└── .env                   # Postgres creds filled in; API keys left blank
```

`config.py` and `database.py` were added beyond the original file list — they
were needed to read `.env` settings and to give the Postgres connection an
actual purpose once Pinecone was chosen as the vector store.

## Design decisions (from your answers)

- **Vector store: Pinecone.** `vectorstore.py` creates/reuses a serverless
  index (`PINECONE_INDEX_NAME`, default `cookbook-rag`) sized to match the
  embedding model's output dimension.
- **Postgres role: app data, not vectors.** Since Pinecone holds the
  embeddings, `swish_db` is used instead to log every `/query` call
  (`ChatLog`: question, answer, sources, timestamp) and every ingest/upload
  (`DocumentRecord`: filename, chunk count, timestamp). Tables are created
  automatically on startup via `init_db()`.
- **LLM/embedding provider: left open.** Nothing is hardcoded. `app/config.py`
  reads `LLM_PROVIDER`, `LLM_MODEL`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`
  from `.env`. `rag.generate_answer()` branches on `openai` / `anthropic`
  using the raw SDKs directly; `vectorstore.embed_texts()` currently supports
  `openai`. Swap models by editing `.env` — no code changes needed for a
  different OpenAI/Anthropic model name.
- **No framework.** LangChain was dropped in favor of a plain flow: `pypdf`
  to extract text, a hand-rolled character chunker, the `openai`/`anthropic`
  SDKs directly for embeddings and generation, and the `pinecone` SDK
  directly for storage/query. Fewer moving parts, easier to read end to end.

## Endpoints

| Method | Path      | Purpose                                              |
|--------|-----------|-------------------------------------------------------|
| POST   | `/ingest` | Load + chunk + embed every PDF in `documents/`        |
| POST   | `/upload` | Upload a single PDF, chunk + embed it                 |
| POST   | `/query`  | Ask a question, get an answer + source list, logged   |
| GET    | `/health` | Liveness check                                         |

## Before running

1. `pip install -r requirements.txt`
2. Drop a `cookbook.pdf` (or any PDFs) into `documents/`
3. Fill in `.env`:
   - `PINECONE_API_KEY`
   - `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` depending on `LLM_PROVIDER`
   - Adjust `LLM_MODEL` / `EMBEDDING_MODEL` if you don't want the defaults
     (`gpt-4o-mini` / `text-embedding-3-small`)
4. Confirm `swish_db` exists on the Postgres instance in `.env` (create it if
   it doesn't — `init_db()` creates tables, not the database itself)

## Run

```bash
cd cookbook-backend
fastapi dev app/main.py
```

Then: `POST /ingest` to index `documents/`, `POST /query` with
`{"question": "..."}` to ask.

## Not yet done

- No auth on any endpoint
- No tests
- `cookbook.pdf` itself — needs to be supplied
- `vector_db/` folder is currently dead weight (kept only because it was in
  the requested structure)
