# Cookbook RAG

A small RAG (Retrieval-Augmented Generation) app: upload cookbook PDFs, ask
questions, and get answers grounded only in what you uploaded.

- **`cookbook-backend/`** — FastAPI service that ingests PDFs, embeds and
  stores their chunks in Pinecone, and answers questions using Gemini.
- **`cookbook-frontend/`** — React + Vite UI for uploading cookbooks and
  chatting with them.

## How it works

1. **Upload / Ingest** — A PDF is uploaded (`POST /upload`) or picked up from
   `cookbook-backend/documents/` (`POST /ingest`). `app/loader.py` extracts
   text with `pypdf`, `app/chunking.py` splits it into character-based
   chunks.
2. **Embed & store** — Each chunk is embedded with Gemini
   (`gemini-embedding-001`) and upserted into a Pinecone serverless index
   (`app/vectorstore.py`). The index is created automatically on first use,
   sized to match the embedding dimension.
3. **Ask** — A question (`POST /query`) is embedded the same way, Pinecone
   returns the most similar chunks, and `app/prompt.py` builds a prompt that
   restricts Gemini (`gemini-3.6-flash`) to answering only from that
   retrieved context. If nothing relevant is found, the app says so instead
   of guessing.
4. **Log** — Every query and every ingest/upload is recorded in Postgres
   (`app/database.py`: `ChatLog`, `DocumentRecord` tables), which also backs
   the "your cookbooks" list and delete action in the UI. Tables are created
   automatically on startup.

### Backend layout

```
cookbook-backend/
├── app/
│   ├── main.py         # FastAPI app + CORS + startup (init_db)
│   ├── routes.py        # /upload, /ingest, /query, /documents, /health
│   ├── rag.py            # Gemini client, ingest + answer_question logic
│   ├── loader.py         # PDF text extraction (pypdf)
│   ├── chunking.py       # Character-based chunker
│   ├── vectorstore.py    # Gemini embeddings + Pinecone upsert/query/delete
│   ├── prompt.py         # System prompt + prompt builder
│   ├── config.py         # Settings, loaded from .env
│   └── database.py       # SQLModel engine/session, tables
├── documents/             # Drop PDFs here for POST /ingest
├── requirements.txt
└── .env
```

### API endpoints

| Method | Path                | Purpose                                   |
|--------|----------------------|--------------------------------------------|
| POST   | `/upload`            | Upload one PDF, chunk + embed + index it   |
| POST   | `/ingest`             | Chunk + embed + index every PDF in `documents/` |
| POST   | `/query`              | Ask a question, get an answer + sources    |
| GET    | `/documents`          | List ingested/uploaded documents           |
| DELETE | `/documents/{id}`     | Remove a document and its vectors          |
| GET    | `/health`             | Liveness check                             |

## Prerequisites

- Python 3.11+
- Node.js 18+
- A Postgres database (e.g. `swish_db`)
- API keys: [Gemini](https://ai.google.dev/) and [Pinecone](https://www.pinecone.io/)

## Running the backend

```bash
cd cookbook-backend
python -m venv venv
venv\Scripts\activate        # Windows (use `source venv/bin/activate` on macOS/Linux)
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in:

- `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`
- `PINECONE_API_KEY` (`PINECONE_INDEX_NAME` defaults to `cookbook-gemini-rag`)
- `GEMINI_API_KEY`

Make sure the Postgres database in `POSTGRES_DB` already exists — the app
creates its tables on startup, not the database itself.

Start the API:

```bash
fastapi dev app/main.py
```

The API listens on `http://127.0.0.1:8000` by default (pass `--port 8001` to
`fastapi dev` if you want to match the frontend's default alternate port).
Optionally seed it from `documents/`:

```bash
curl -X POST http://127.0.0.1:8000/ingest
```

## Running the frontend

```bash
cd cookbook-frontend
npm install
```

Copy `.env.example` to `.env` and set `VITE_API_BASE_URL` to your backend URL
(e.g. `http://127.0.0.1:8000`). If unset, the frontend tries
`http://127.0.0.1:8000` then `http://127.0.0.1:8001` automatically.

```bash
npm run dev
```

Open `http://localhost:5173`, upload a cookbook PDF, and ask a question.

## Notes

- Answers are strictly grounded in uploaded documents — if nothing relevant
  is found, the API returns a "couldn't find that" message rather than
  inventing one.
- There is no authentication on any endpoint; this is a proof-of-concept.
