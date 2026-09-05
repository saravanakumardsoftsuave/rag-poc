# RAG Eval Failure Analysis — 2026-09-05

19 questions tested against the cookbook RAG pipeline (Pinecone hybrid retrieval +
local `sentence-transformers/all-MiniLM-L6-v2` embeddings + local
`Qwen/Qwen2.5-0.5B-Instruct` for generation). 10 correct, 9 wrong.

For each failure, "Retrieval failure" means the chunk(s) needed to answer
correctly were never handed to the LLM in the first place (`hybrid_search` in
`app/retrieval.py` didn't surface them in its top `hybrid_top_k` = 20). "Generation
failure" means the correct chunk(s) almost certainly *were* in context, but the
0.5B model still answered wrong — misreading, conflating entities, or
hallucinating over it. These are inferred from corpus structure and from which
other questions about the same recipe succeeded, not from a captured log of the
actual chunks sent per query (no per-query retrieval logging exists yet — see
Recommendation 3).

## Failures

### 1. "Difference between Dal Makhani and Sambar in terms of main lentils?"
- **Answer given:** reversed which dish uses which lentil.
- **Classification: Generation failure.**
- Both recipes were separately answered correctly elsewhere (Dal Makhani's
  25-min simmer time, Sambar's tempering ingredients, Sambar's toor dal use),
  so their chunks are retrievable. This question asks the model to hold two
  similar entities in mind at once and not swap their attributes — exactly
  the kind of cross-entity confusion small instruct models are prone to.

### 2. "Which recipes from both collections contain cardamom?"
- **Answer given:** hallucinated cardamom into 5 dishes that don't have it,
  duplicated some recipe names.
- **Classification: Retrieval-design failure (primary), generation failure
  (secondary).**
- This is an aggregation/filter query ("for every recipe, check for X"), not a
  single-fact lookup. Top-k hybrid retrieval can only ever return a fixed
  slice of chunks ranked by relevance to the literal query text — it has no
  way to guarantee *every* recipe chunk mentioning cardamom is in that slice,
  so the retrieved set was already an incomplete, arbitrary sample of the
  corpus. The model then compounded that by inventing coverage for dishes it
  never actually saw evidence for.

### 3. "Does Jeera Rice contain tamarind?"
- **Answer given:** "yes" + invented unrelated ingredients.
- **Classification: Generation failure.**
- Jeera Rice's ingredient list was correctly retrieved and quoted for a
  different question ("cooking time for Jeera Rice"), so its chunk is
  reachable by retrieval. Here the model failed at negation ("X does NOT
  contain Y") and fabricated ingredients instead of just reading the list
  that was in front of it.

### 4. "Does Sambar use paneer as an ingredient?"
- **Answer given:** "yes."
- **Classification: Generation failure.**
- Sambar's ingredient/tempering chunks are demonstrably retrievable (used
  correctly in two other questions). Same negation-handling failure as #3.

### 5. "Does Gulab Jamun use fermented batter?"
- **Answer given:** "yes."
- **Classification: Generation failure.**
- No fermentation is mentioned anywhere in a khoya-dough dessert recipe; the
  model asserted it anyway. Same negation-failure pattern as #3 and #4 — the
  model defaults to "yes" on yes/no questions about absent attributes rather
  than checking the context.

### 6. "Fermentation time for Aloo Paratha?"
- **Answer given:** confused the 15-minute dough rest with a fermentation
  step, mixed in the recipe's prep/cook times.
- **Classification: Generation failure.**
- The relevant numbers (15-min rest, 20-min prep, 20-min cook) are all in one
  place in the source recipe — the model had the right chunk but attributed
  the wrong field to "fermentation time."

### 7. "Which recipe recommends adding a used tea bag while cooking?"
- **Answer given:** failed to name Chole; gave unrelated recipes.
- **Classification: Retrieval failure (most likely).**
- The tea-bag tip is a minor aside inside Chole's chunk, not its main
  ingredient/method text. With reranking removed from `retrieval.py` (per an
  earlier request in this project) there is nothing left to promote a
  low-semantic-similarity, high-lexical-specificity chunk like this one into
  the top 20 — it's plausible this chunk simply didn't make the cut RRF
  fusion handed to the model, so it had nothing to work with.

### 8. "Which dish should not be boiled vigorously?"
- **Answer given:** Masala Dosa (correct answer: Rasam).
- **Classification: Generation failure (most likely), with a retrieval
  contributing factor.**
- Rasam's content is retrievable (correctly used to answer the toor-dal
  question), so its chunk was probably in context; the model picked the
  wrong dish out of the several recipes it was holding at once. Can't fully
  rule out the specific "don't boil vigorously" sentence living in a
  chunk that missed the top 20, given no reranking is active.

### 9. "Recipe for Butter Chicken?"
- **Answer given:** a fabricated, unrelated chicken recipe (soy sauce,
  sesame oil, wok, cornstarch) instead of "not in the documents."
- **Classification: Generation failure, exposing a retrieval/orchestration
  gap.**
- Butter Chicken genuinely isn't in the corpus, so no amount of retrieval
  tuning produces a correct positive match — retrieval correctly has nothing
  good to return. But `answer_question()` in `app/rag.py` only ever returns
  the built-in "not found" fallback when retrieval returns *zero* chunks;
  `hybrid_search` always returns its top 20 nearest chunks regardless of how
  irrelevant they are, so the model was still handed 20 chunks of unrelated
  content and expected to recognize on its own that none of it answers the
  question. A 0.5B model isn't reliable at that judgment call and hallucinated
  a plausible-sounding answer instead of refusing.

## Pattern summary

| Root cause | Count | Questions |
|---|---|---|
| Generation failure (small-model limits: negation, entity-swap, attribution, refusal) | 7 | 1, 3, 4, 5, 6, 8, 9 |
| Retrieval failure or retrieval-design limitation | 2 (+1 contributing) | 2, 7 (8 partial) |

The dominant failure mode by far is the generation model, not retrieval: most
of the *content* needed to answer correctly was reachable, but
`Qwen/Qwen2.5-0.5B-Instruct` (see `HF_GENERATION_MODEL` in `.env`) isn't
reliable at negation ("does X contain Y" → no), holding multiple similar
entities apart, or refusing to answer when nothing relevant is present. The
retrieval-side issues (aggregation queries, and no reranking to rescue
low-semantic/high-lexical chunks) are real but affect a smaller share of
cases.

## Recommendations

1. **Applied — larger local generation model.** `HF_GENERATION_MODEL` moved
   from `Qwen2.5-0.5B-Instruct` to `Qwen2.5-1.5B-Instruct` in `app/config.py`
   and `.env.example` — directly targets the dominant failure category
   (negation, entity-swap, attribution errors, categories 1/3/4/5/6/8).
2. **Applied — cross-encoder reranker reintroduced.** `app/retrieval.py` now
   fuses semantic + keyword via RRF over a wider candidate pool
   (`rerank_candidate_pool`, default 40) and reranks that pool with
   `cross-encoder/ms-marco-MiniLM-L-6-v2` before truncating to
   `hybrid_top_k`, so lexically-specific but low-semantic-similarity chunks
   (like the tea-bag tip) get a fair shot instead of being cut by RRF rank
   alone.
3. **Applied — relevance-score cutoff.** `answer_question()` in `app/rag.py`
   now checks the raw Pinecone cosine similarity of the best dense match
   (returned by `hybrid_search` alongside its results) against
   `relevance_score_cutoff` (default 0.35) before generating; below that it
   returns the "not found" fallback directly. Uses the raw pre-fusion score,
   not the RRF-fused score, since RRF only reflects rank and can't tell "no
   good match" from "best of a bad lot" — targets the Butter Chicken failure
   mode. **The 0.35 default is a starting guess and needs calibration**
   against real query logs (see #4).
4. **Applied — per-query retrieval logging.** `answer_question()` logs the
   query, best semantic score, and each retrieved chunk's id/source/RRF/rerank
   scores; `app/main.py` now calls `logging.basicConfig(level=logging.INFO)`
   so these actually surface. Future eval failures can be classified from
   logged evidence instead of inference, and the logs are what should be used
   to tune #3's cutoff.
5. **Not yet applied — prompt fixes.** `app/prompt.py`'s system prompt now
   explicitly instructs: don't default to "yes" on unstated attributes
   (targets 3/4/5), only report a value under the exact term the question
   asks about (targets 6), and resolve each entity separately before
   comparing two dishes (targets 1) — with a worked example matching the
   Dal Makhani/Sambar case directly. This is a prompt-level mitigation, not a
   fix for the model's underlying capacity limit, so re-run the eval to see
   how much it actually moves the categories above.
6. **Not yet applied — metadata-based filtering for aggregation queries**
   (failure 2, "which recipes contain cardamom"). Top-k retrieval structurally
   cannot answer "check every recipe for X" — it only returns a relevance-
   ranked slice, never a guaranteed-complete one. Needs an ingestion-time
   change: extract each recipe's ingredient list into Pinecone chunk
   metadata, and route "which recipes contain X" style queries to a metadata
   filter instead of semantic/hybrid search. Requires re-ingesting existing
   documents, so left for a follow-up.
